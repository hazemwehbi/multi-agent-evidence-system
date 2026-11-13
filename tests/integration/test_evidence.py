import asyncio
import json
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.config import Settings
from app.models.contracts import EvidenceRef, ExecutionStatus, RunRecord, RunRequest
from app.models.workflow import AnalysisResult
from app.orchestrator.documents import run_documents
from app.services.ingestion import DocumentIngestor, IngestionError, MAX_BYTES
from app.services.repository import EvidenceRepository, RepositoryError


def test_ingestion_preserves_unicode_crlf_offsets_and_markdown_sections():
    parser = DocumentIngestor()
    original = "# Résumé\r\n\r\nBudget €20.\r\n\r\n## Timing\r\n\r\nMay."
    data = original.encode()
    md = parser.parse("pilot.md", data)
    assert md == parser.parse("pilot.md", data)
    assert md.source.text == original
    assert md.source.source_id != parser.parse("pilot.md", data + b"!").source.source_id
    assert md.source.source_id != parser.parse("other.md", data).source.source_id
    assert [(p.text, p.section) for p in md.passages] == [
        ("# Résumé", "Résumé"), ("Budget €20.", "Résumé"),
        ("## Timing", "Timing"), ("May.", "Timing"),
    ]
    for passage in md.passages:
        assert original[passage.start:passage.end] == passage.text
        assert passage.ref.passage_id == f"{passage.start}-{passage.end}"
    txt = parser.parse("pilot.txt", data)
    assert txt.media_type == "text/plain"
    assert all(p.section is None for p in txt.passages)


@pytest.mark.parametrize(("name", "data"), [
    ("a.txt", b""), ("a.md", b" \r\n"), ("a.txt", b"\xff"),
    ("a.txt", b"abc\0"), ("a.pdf", b"data"), ("a.txt", b"x" * (MAX_BYTES + 1)),
])
def test_rejects_invalid_documents(name, data):
    with pytest.raises(IngestionError):
        DocumentIngestor().parse(name, data)


def test_failed_ingestion_is_atomic(tmp_path):
    db_path = tmp_path / "evidence.sqlite"
    repository = EvidenceRepository(db_path)
    first = DocumentIngestor().parse("a.txt", b"First")
    second = DocumentIngestor().parse("b.md", b"Second")
    bad = second.passages[0].model_copy(update={"text": "Forged"})
    with pytest.raises(RepositoryError, match="match the original"):
        repository.ingest((first, second.model_copy(update={"passages": (bad,)})))
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT count(*) FROM sources").fetchone() == (0,)
        assert db.execute("SELECT count(*) FROM passages").fetchone() == (0,)
    with pytest.raises(IngestionError, match="Could not read"):
        DocumentIngestor().read(tmp_path / "missing.txt")


def test_missing_source_prevents_run_creation(tmp_path):
    repository = EvidenceRepository(tmp_path / "evidence.sqlite")
    record = RunRecord(
        run_id=uuid4(), request=RunRequest(question="Budget", source_ids=("unknown",)),
        model=Settings().model_metadata(), started_at=datetime.now(UTC),
        status=ExecutionStatus.RUNNING,
    )
    with pytest.raises(RepositoryError):
        repository.start(record)
    with pytest.raises(RepositoryError, match="Unknown run"):
        repository.inspect(record.run_id)
    with pytest.raises(RepositoryError, match="outside"):
        repository.search(record.run_id, "unknown", "budget")


def test_cli_restart_and_claim_provenance(tmp_path):
    cedar = tmp_path / "cedar.txt"
    birch = tmp_path / "birch.md"
    cedar.write_bytes("Cedar budget €20.".encode())
    original = "# Pilot\r\n\r\nBirch budget €24.\r\n"
    birch.write_bytes(original.encode())
    db = tmp_path / "evidence.sqlite"

    def cli(command, *args):
        result = subprocess.run(
            [sys.executable, "-X", "utf8", "-m", "app.cli", command, "--db", str(db), *map(str, args)],
            check=True, capture_output=True, text=True, encoding="utf-8", timeout=10,
        )
        return json.loads(result.stdout)

    result = cli("run", "--question", "What is the budget?", cedar, birch)
    run = result["run"]["run_id"]
    assert cli("inspect", run) == result
    assert result["run"]["model"]["provider"] == "offline"
    claims = next(m for m in result["messages"] if "claims" in m["content"])
    assert len(claims["content"]["claims"]) == 2
    candidate = claims["content"]["claims"][1]
    trace = cli("trace", run, candidate["claim_id"])
    assert trace["analysis_message_id"] == claims["message_id"]
    evidence = trace["evidence"][0]
    passage = evidence["passage"]
    assert passage["ref"] == candidate["evidence_refs"][0]
    assert evidence["document_name"] == "birch.md"
    assert passage["section"] == "Pilot"
    assert passage["text"] == original[passage["start"]:passage["end"]]
    retrieved = next(m for m in result["messages"] if m["message_id"] == evidence["retrieval_message_id"])
    assert passage == retrieved["content"]["passages"][0]["passage"]
    second = cli("run", "--question", "budget", cedar)
    repository = EvidenceRepository(db)
    second_id = UUID(second["run"]["run_id"])
    with pytest.raises(RepositoryError, match="does not belong"):
        repository.trace_claim(second_id, UUID(candidate["claim_id"]))
    with pytest.raises(RepositoryError, match="outside"):
        repository.search(second_id, passage["ref"]["source_id"], "budget")


def test_failed_trace_write_rolls_back_and_marks_run_failed(tmp_path, monkeypatch):
    path = tmp_path / "pilot.txt"
    path.write_bytes(b"Pilot budget is 20.")
    db_path = tmp_path / "evidence.sqlite"
    repository = EvidenceRepository(db_path)
    finish = repository.finish
    run_id = None

    def inject_bad_claim(report):
        nonlocal run_id
        run_id = report.run.run_id
        messages = list(report.messages)
        index = next(i for i, m in enumerate(messages) if isinstance(m.content, AnalysisResult))
        message = messages[index]
        claim = message.content.claims[0].model_copy(update={
            "evidence_refs": (EvidenceRef(source_id="synthetic", passage_id="forged"),),
        })
        messages[index] = message.model_copy(update={"content": AnalysisResult(claims=(claim,))})
        finish(report.model_copy(update={"messages": tuple(messages)}))

    monkeypatch.setattr(repository, "finish", inject_bad_claim)
    with pytest.raises(RepositoryError):
        asyncio.run(run_documents(Settings(), repository, "budget", (path,)))
    assert EvidenceRepository(db_path).inspect(run_id).status == ExecutionStatus.FAILED
    with sqlite3.connect(db_path) as db:
        for table in ("tasks", "messages", "retrievals", "claims", "claim_evidence"):
            assert db.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)


def test_rejects_unusable_database_path(tmp_path):
    with pytest.raises(RepositoryError, match="SQLite operation failed"):
        EvidenceRepository(tmp_path / "missing-parent" / "evidence.sqlite")
