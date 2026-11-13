import re
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

from app.models.contracts import EvidenceRef, ExecutionStatus, Passage, RunRecord, SourceDocument
from app.models.workflow import AnalysisResult, Plan, RetrievalResult, TaskInput, WorkflowReport
from app.services.ingestion import ParsedDocument

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, media_type TEXT NOT NULL, text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS passages (
    source_id TEXT REFERENCES sources(id), id TEXT, start_offset INTEGER NOT NULL,
    end_offset INTEGER NOT NULL, section TEXT, text TEXT NOT NULL,
    PRIMARY KEY (source_id, id)
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, status TEXT NOT NULL, record_json TEXT NOT NULL, report_json TEXT
);
CREATE TABLE IF NOT EXISTS run_sources (
    run_id TEXT REFERENCES runs(id), source_id TEXT REFERENCES sources(id),
    PRIMARY KEY (run_id, source_id)
);
CREATE TABLE IF NOT EXISTS tasks (
    run_id TEXT REFERENCES runs(id), id TEXT, role TEXT NOT NULL, task_json TEXT NOT NULL,
    PRIMARY KEY (run_id, id)
);
CREATE TABLE IF NOT EXISTS messages (
    run_id TEXT, id TEXT, ordinal INTEGER NOT NULL, task_id TEXT NOT NULL, parent_id TEXT,
    message_json TEXT NOT NULL, PRIMARY KEY (run_id, id), UNIQUE (run_id, ordinal),
    FOREIGN KEY (run_id, task_id) REFERENCES tasks(run_id, id),
    FOREIGN KEY (run_id, parent_id) REFERENCES messages(run_id, id)
);
CREATE TABLE IF NOT EXISTS retrievals (
    run_id TEXT, message_id TEXT NOT NULL, source_id TEXT, passage_id TEXT,
    PRIMARY KEY (run_id, source_id, passage_id),
    FOREIGN KEY (run_id, message_id) REFERENCES messages(run_id, id),
    FOREIGN KEY (run_id, source_id) REFERENCES run_sources(run_id, source_id),
    FOREIGN KEY (source_id, passage_id) REFERENCES passages(source_id, id)
);
CREATE TABLE IF NOT EXISTS claims (
    run_id TEXT, id TEXT, message_id TEXT NOT NULL, statement TEXT NOT NULL,
    PRIMARY KEY (run_id, id),
    FOREIGN KEY (run_id, message_id) REFERENCES messages(run_id, id)
);
CREATE TABLE IF NOT EXISTS claim_evidence (
    run_id TEXT, claim_id TEXT, source_id TEXT, passage_id TEXT,
    PRIMARY KEY (run_id, claim_id, source_id, passage_id),
    FOREIGN KEY (run_id, claim_id) REFERENCES claims(run_id, id),
    FOREIGN KEY (run_id, source_id, passage_id) REFERENCES retrievals(run_id, source_id, passage_id)
);
"""


class RepositoryError(ValueError):
    pass


STOP_WORDS = frozenset("a an and are can compare for in is of on or the to what which with".split())


def _terms(text: str) -> set[str]:
    return set(re.findall(r"[^\W_]+", text.casefold())) - STOP_WORDS


class EvidenceRepository:
    def __init__(self, path: Path) -> None:
        self.path = path
        with self._connection() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        try:
            db = sqlite3.connect(self.path)
            try:
                db.row_factory = sqlite3.Row
                db.execute("PRAGMA foreign_keys = ON")
                with db:
                    yield db
            finally:
                db.close()
        except sqlite3.Error as exc:
            raise RepositoryError(f"SQLite operation failed ({type(exc).__name__})") from exc

    def ingest(self, documents: Sequence[ParsedDocument]) -> tuple[str, ...]:
        with self._connection() as db:
            for document in documents:
                source = document.source
                db.execute(
                    "INSERT INTO sources VALUES (?, ?, ?, ?) ON CONFLICT(id) DO NOTHING",
                    (source.source_id, source.document_name, document.media_type, source.text),
                )
                for passage in document.passages:
                    if (passage.ref.source_id != source.source_id
                        or passage.end > len(source.text)
                        or source.text[passage.start:passage.end] != passage.text):
                        raise RepositoryError("Passage does not match the original source")
                    db.execute(
                        "INSERT INTO passages VALUES (?, ?, ?, ?, ?, ?) "
                        "ON CONFLICT(source_id, id) DO NOTHING",
                        (source.source_id, passage.ref.passage_id, passage.start,
                         passage.end, passage.section, passage.text),
                    )
        return tuple(dict.fromkeys(item.source.source_id for item in documents))

    def start(self, run: RunRecord) -> None:
        with self._connection() as db:
            db.execute("INSERT INTO runs VALUES (?, ?, ?, NULL)",
                       (str(run.run_id), run.status, run.model_dump_json()))
            db.executemany("INSERT INTO run_sources VALUES (?, ?)",
                           ((str(run.run_id), source) for source in run.request.source_ids))

    def fail(self, run: RunRecord) -> None:
        failed = run.model_copy(update={"status": ExecutionStatus.FAILED})
        with self._connection() as db:
            db.execute("UPDATE runs SET status = ?, record_json = ? WHERE id = ? AND status = 'running'",
                       (failed.status, failed.model_dump_json(), str(run.run_id)))

    def _resolve(self, db: sqlite3.Connection, ref: EvidenceRef) -> tuple[SourceDocument, Passage]:
        row = db.execute(
            "SELECT s.name, s.text AS original, p.* FROM passages p JOIN sources s "
            "ON s.id = p.source_id WHERE p.source_id = ? AND p.id = ?",
            (ref.source_id, ref.passage_id),
        ).fetchone()
        if row is None:
            raise RepositoryError("Unknown source or passage reference")
        start, end = row["start_offset"], row["end_offset"]
        if end > len(row["original"]) or row["original"][start:end] != row["text"]:
            raise RepositoryError("Stored passage does not match its source")
        return (
            SourceDocument(source_id=ref.source_id, document_name=row["name"], text=row["original"]),
            Passage(ref=ref, start=start, end=end, section=row["section"], text=row["text"]),
        )

    def resolve_for_run(self, run_id: UUID, ref: EvidenceRef) -> Passage:
        with self._connection() as db:
            if db.execute(
                "SELECT 1 FROM run_sources WHERE run_id = ? AND source_id = ?",
                (str(run_id), ref.source_id),
            ).fetchone() is None:
                raise RepositoryError("Source is outside the run scope")
            return self._resolve(db, ref)[1]

    def retrieved_passage(self, run_id: UUID, ref: EvidenceRef) -> dict:
        with self._connection() as db:
            row = db.execute(
                "SELECT message_id FROM retrievals WHERE run_id = ? AND source_id = ? AND passage_id = ?",
                (str(run_id), ref.source_id, ref.passage_id),
            ).fetchone()
            if row is None:
                raise RepositoryError("Passage was not retrieved by this run")
            source, passage = self._resolve(db, ref)
            return {
                "document_name": source.document_name, "original_text": source.text,
                "passage": passage.model_dump(mode="json"), "retrieval_message_id": row["message_id"],
            }

    def search(self, run_id: UUID, source_id: str, objective: str) -> tuple[tuple[str, Passage], ...]:
        terms = _terms(objective)
        with self._connection() as db:
            scope = db.execute("SELECT 1 FROM run_sources WHERE run_id = ? AND source_id = ?",
                               (str(run_id), source_id)).fetchone()
            if scope is None:
                raise RepositoryError("Source is outside the run scope")
            rows = db.execute(
                "SELECT id, text, start_offset FROM passages WHERE source_id = ?", (source_id,),
            )
            ranked = []
            for row in rows:
                overlap = terms & _terms(row["text"])
                if overlap:
                    ranked.append((-len(overlap), row["start_offset"], row["id"]))
            results = []
            for _, _, passage_id in sorted(ranked)[:2]:
                source, passage = self._resolve(db, EvidenceRef(source_id=source_id, passage_id=passage_id))
                results.append((source.document_name, passage))
            return tuple(results)

    def finish(self, report: WorkflowReport) -> None:
        run_id = str(report.run.run_id)
        with self._connection() as db:
            dispatched: dict[str, TaskInput] = {}
            for ordinal, message in enumerate(report.messages):
                task_id = str(message.task_id)
                content = message.content
                db.execute(
                    "INSERT INTO tasks VALUES (?, ?, ?, ?) ON CONFLICT(run_id, id) DO NOTHING",
                    (run_id, task_id, message.recipient_agent, content.model_dump_json()),
                )
                if isinstance(content, Plan):
                    db.executemany(
                        "INSERT INTO tasks VALUES (?, ?, ?, ?)",
                        ((run_id, str(task.task_id), task.agent, task.model_dump_json())
                         for task in content.tasks),
                    )
                parent = str(message.parent_message_id) if message.parent_message_id else None
                if isinstance(content, TaskInput):
                    dispatched[str(message.message_id)] = content
                db.execute("INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?)",
                           (run_id, str(message.message_id), ordinal, task_id,
                            parent, message.model_dump_json()))
                for ref in message.evidence_refs:
                    self._resolve(db, ref)
                    if db.execute(
                        "SELECT 1 FROM run_sources WHERE run_id = ? AND source_id = ?",
                        (run_id, ref.source_id),
                    ).fetchone() is None:
                        raise RepositoryError("Message evidence is outside the run scope")
                if isinstance(content, RetrievalResult):
                    assignment = dispatched.get(parent or "")
                    if assignment is None:
                        raise RepositoryError("Retrieval result has no dispatch")
                    for item in content.passages:
                        ref = item.passage.ref
                        if ref.source_id != assignment.task.source_id:
                            raise RepositoryError("Retrieval is outside its assigned source")
                        source, stored = self._resolve(db, ref)
                        if stored != item.passage or source.document_name != item.document_name:
                            raise RepositoryError("Retrieval does not match the stored passage")
                        db.execute("INSERT INTO retrievals VALUES (?, ?, ?, ?)",
                                   (run_id, str(message.message_id), ref.source_id, ref.passage_id))
                if isinstance(content, AnalysisResult):
                    assignment = dispatched.get(parent or "")
                    if assignment is None:
                        raise RepositoryError("Analysis result has no dispatch")
                    retrieved = {
                        item.passage.ref
                        for upstream in assignment.upstream
                        if isinstance(upstream.content, RetrievalResult)
                        for item in upstream.content.passages
                    }
                    for claim in content.claims:
                        if not set(claim.evidence_refs) <= retrieved:
                            raise RepositoryError("Claim cites a passage absent from its retrieval inputs")
                        db.execute("INSERT INTO claims VALUES (?, ?, ?, ?)",
                                   (run_id, str(claim.claim_id), str(message.message_id), claim.statement))
                        db.executemany("INSERT INTO claim_evidence VALUES (?, ?, ?, ?)", (
                            (run_id, str(claim.claim_id), ref.source_id, ref.passage_id)
                            for ref in claim.evidence_refs
                        ))
            updated = db.execute(
                "UPDATE runs SET status = ?, record_json = ?, report_json = ? "
                "WHERE id = ? AND status = 'running'",
                (report.run.status, report.run.model_dump_json(), report.model_dump_json(), run_id),
            )
            if updated.rowcount != 1:
                raise RepositoryError("Run is missing or already finalized")

    def inspect(self, run_id: UUID) -> WorkflowReport | RunRecord:
        with self._connection() as db:
            row = db.execute("SELECT record_json, report_json FROM runs WHERE id = ?",
                             (str(run_id),)).fetchone()
        if row is None:
            raise RepositoryError("Unknown run")
        if row["report_json"] is None:
            return RunRecord.model_validate_json(row["record_json"])
        return WorkflowReport.model_validate_json(row["report_json"])

    def trace_claim(self, run_id: UUID, claim_id: UUID) -> dict:
        with self._connection() as db:
            args = (str(run_id), str(claim_id))
            claim = db.execute(
                "SELECT statement, message_id FROM claims WHERE run_id = ? AND id = ?", args,
            ).fetchone()
            if claim is None:
                raise RepositoryError("Claim does not belong to this run")
            rows = db.execute(
                "SELECT e.source_id, e.passage_id, r.message_id FROM claim_evidence e "
                "JOIN retrievals r USING (run_id, source_id, passage_id) "
                "WHERE e.run_id = ? AND e.claim_id = ? ORDER BY e.source_id, e.passage_id", args,
            )
            evidence = []
            for row in rows:
                ref = EvidenceRef(source_id=row["source_id"], passage_id=row["passage_id"])
                source, passage = self._resolve(db, ref)
                evidence.append({
                    "document_name": source.document_name, "passage": passage.model_dump(mode="json"),
                    "retrieval_message_id": row["message_id"],
                })
        return {"run_id": str(run_id), "claim_id": str(claim_id), "statement": claim["statement"],
                "analysis_message_id": claim["message_id"], "evidence": evidence}
