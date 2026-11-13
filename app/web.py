import asyncio
import json
import os
from contextlib import asynccontextmanager
from html import escape
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.datastructures import UploadFile

from app.config import Settings
from app.models.contracts import EvidenceRef
from app.models.workflow import AnalysisResult, WorkflowReport
from app.orchestrator.documents import run_parsed
from app.services.ingestion import DocumentIngestor, IngestionError, MAX_BYTES
from app.services.model import ModelError
from app.services.repository import EvidenceRepository, RepositoryError

MAX_BODY = 16 * MAX_BYTES + 65536


def _page(title: str, content: str, *, status: int = 200, refresh: bool = False) -> HTMLResponse:
    refresh_tag = '<meta http-equiv="refresh" content="2">' if refresh else ""
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">{refresh_tag}
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} · MAEDS</title>
<style>
body{{font-family:system-ui,sans-serif;color:#182831;background:#f4f7f6;margin:0}}
main{{max-width:54rem;margin:3rem auto;padding:0 1.25rem}}
nav{{margin-bottom:2rem}}a{{color:#145c54}}label{{display:block;font-weight:600;margin-top:1rem}}
textarea{{display:block;box-sizing:border-box;width:100%;padding:.75rem;min-height:7rem}}
button{{display:block;margin-top:1.25rem;padding:.65rem 1rem;background:#145c54;color:white;border:0}}
article,details,form{{background:white;border:1px solid #ccd9d5;padding:1rem;margin:1rem 0}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere}}li{{margin:.5rem 0}}
</style></head><body><main><nav><a href="/">MAEDS</a></nav><h1>{escape(title)}</h1>{content}</main></body></html>""",
        status_code=status)


def _render_run(report: WorkflowReport) -> HTMLResponse:
    claims = {
        claim.claim_id: claim
        for message in report.messages if isinstance(message.content, AnalysisResult)
        for claim in message.content.claims
    }
    considered = report.result.decision.considered if report.result else ()
    findings, disclosures = [], []
    for item in considered:
        record = item.verification
        claim = claims.get(record.claim_id)
        if claim is None:
            continue
        assessment = record.assessment
        entries = []
        for label, refs in (
            ("Cited", record.citations.resolved_refs), ("Supporting", assessment.supporting_refs),
            ("Contradicting", assessment.contradicting_refs),
        ):
            for ref in refs:
                href = f"/runs/{report.run.run_id}/evidence/{escape(ref.source_id)}/{escape(ref.passage_id)}"
                entries.append(f'<li>{label} <a href="{href}">{escape(ref.passage_id)}</a></li>')
        issues = "".join(f"<li>{escape(issue.reason)}</li>" for issue in record.citations.issues)
        block = (
            f"<article><strong>{escape(assessment.label)}</strong>"
            f"<blockquote>{escape(claim.statement)}</blockquote>"
            f"<p>{escape(assessment.explanation)}</p><p>{escape(item.reason)}</p>"
            f"<ul>{''.join(entries)}{issues}</ul></article>"
        )
        (findings if item.eligible else disclosures).append(block)
    trace = escape(json.dumps([m.model_dump(mode="json") for m in report.messages], indent=2))
    decision = ""
    if report.result:
        record = report.result.decision
        decision = (
            f"<p>Decision: {escape(record.outcome.replace('_', ' '))}.</p>"
            "<p>The workflow abstained from making a recommendation.</p>"
            f"<details><summary>Decision record</summary><pre>{escape(record.model_dump_json(indent=2))}</pre></details>"
        )
    return _page("Run result", (
        f"<p>{escape(report.run.request.question)}</p><p>Status: {escape(report.run.status)}.</p>"
        f"{decision}<h2>Verified findings</h2>{''.join(findings) or '<p>No eligible findings.</p>'}"
        f"<h2>Qualified and unresolved claims</h2>{''.join(disclosures) or '<p>None.</p>'}"
        f"<details><summary>Execution trace</summary><pre>{trace}</pre></details>"
    ))


def create_app(database: Path | None = None, settings: Settings | None = None) -> FastAPI:
    path = database or Path(os.environ.get("MAEDS_DB", "evidence.sqlite"))
    jobs: set[asyncio.Task] = set()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        pending = tuple(jobs)
        for job in pending:
            job.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    app = FastAPI(title="MAEDS", lifespan=lifespan)

    @app.get("/", response_class=HTMLResponse)
    async def home():
        return _page("Evidence review", """
<form method="post" action="/runs" enctype="multipart/form-data">
<label for="question">Question</label>
<textarea id="question" name="question" maxlength="2000" required></textarea>
<label for="files">Documents</label>
<input type="file" id="files" name="files" accept=".txt,.md" multiple required>
<p>Choose up to 16 UTF-8 TXT or Markdown files, each up to 256 KiB.</p>
<button type="submit">Start run</button></form>""")

    @app.post("/runs")
    async def submit(request: Request):
        # Limit bytes before handing the multipart body to the parser.
        size = 0
        chunks = []
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_BODY:
                raise HTTPException(413, "Upload exceeds the request limit")
            chunks.append(chunk)
        body = b"".join(chunks)

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        bounded = Request(request.scope, receive)
        parser = DocumentIngestor()
        try:
            async with bounded.form(max_files=16, max_fields=1, max_part_size=8192) as form:
                question = form.get("question")
                if not isinstance(question, str) or not question.strip() or len(question) > 2000:
                    raise IngestionError("Supply a question of up to 2,000 characters")
                files = form.getlist("files")
                if not files or any(not isinstance(f, UploadFile) for f in files):
                    raise IngestionError("Supply at least one TXT or Markdown file")
                documents = []
                for file in files:
                    name = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
                    documents.append(parser.parse(name, await file.read(MAX_BYTES + 1)))
        except IngestionError as exc:
            return _page("Upload rejected", f"<p>{escape(str(exc))}</p>", status=400)

        started = asyncio.get_running_loop().create_future()

        async def execute():
            try:
                await run_parsed(
                    settings or Settings(), EvidenceRepository(path), question, tuple(documents),
                    on_start=lambda record: started.set_result(record.run_id),
                )
            except Exception as exc:
                if not started.done():
                    started.set_exception(exc)

        job = asyncio.create_task(execute())
        jobs.add(job)
        job.add_done_callback(jobs.discard)
        try:
            run_id = await asyncio.shield(started)
        except (ModelError, RepositoryError, ValueError):
            raise HTTPException(503, "Unable to start the workflow") from None
        return RedirectResponse(f"/runs/{run_id}", status_code=303)

    def inspect(run_id: UUID):
        try:
            return EvidenceRepository(path).inspect(run_id)
        except RepositoryError:
            raise HTTPException(404, "Run unavailable") from None

    @app.get("/api/runs/{run_id}")
    async def run_json(run_id: UUID):
        return inspect(run_id)

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    async def run_page(run_id: UUID):
        report = inspect(run_id)
        if isinstance(report, WorkflowReport):
            return _render_run(report)
        return _page("Run status", f"<p>Status: {escape(report.status)}.</p>",
                     refresh=report.status == "running")

    @app.get("/runs/{run_id}/evidence/{source_id}/{passage_id}", response_class=HTMLResponse)
    async def passage_page(run_id: UUID, source_id: str, passage_id: str):
        try:
            data = EvidenceRepository(path).retrieved_passage(
                run_id, EvidenceRef(source_id=source_id, passage_id=passage_id),
            )
        except (RepositoryError, ValueError):
            raise HTTPException(404, "Passage unavailable for this run") from None
        passage = data["passage"]
        original = data["original_text"]
        start, end = passage["start"], passage["end"]
        return _page(data["document_name"], (
            f'<p><a href="/runs/{run_id}">Back to run</a></p>'
            f"<p>Section: {escape(passage['section'] or '—')}. Character offsets [{start}, {end}).</p>"
            f"<h2>Passage</h2><pre>{escape(passage['text'])}</pre><h2>Original source</h2>"
            f"<pre>{escape(original[:start])}<mark>{escape(original[start:end])}</mark>{escape(original[end:])}</pre>"
        ))

    return app
