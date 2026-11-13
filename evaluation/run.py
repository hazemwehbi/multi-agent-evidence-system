import argparse
import asyncio
import hashlib
import json
import platform
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from tempfile import TemporaryDirectory
from time import perf_counter
from uuid import uuid4

from pydantic import BaseModel

from app.agents.synthesis import SynthesisAgent
from app.agents.verification import VerificationAgent
from app.config import Settings
from app.models.contracts import (
    AgentMessage, AgentRole, Claim, Contract, EvidenceRef, ExecutionStatus, MessageType,
    RetrievedPassage, RunRecord, RunRequest,
)
from app.models.workflow import AnalysisResult, RetrievalResult, TaskInput, WorkflowTask
from app.orchestrator.documents import OfflineDocumentBackend, run_parsed
from app.services.ingestion import DocumentIngestor
from app.services.model import ModelClient, ModelRequest
from app.services.repository import EvidenceRepository
from evaluation.metrics import release_metrics, score

DATASET = Path(__file__).with_name("v1.json")


class FaultBackend:
    def __init__(self, fault):
        self.fault = fault

    async def generate(self, request: ModelRequest, schema: type[BaseModel]) -> object:
        if self.fault == "failure":
            raise RuntimeError("Injected evaluation fault")
        if self.fault == "timeout":
            await asyncio.Future()
        return {"label": "invalid"}


def envelope(run_id, role, content: Contract):
    return AgentMessage[type(content)](
        message_id=uuid4(), run_id=run_id, task_id=uuid4(), sender_agent=role,
        recipient_agent=AgentRole.COORDINATOR, message_type=MessageType.RESULT,
        timestamp=datetime.now(UTC), execution_status=ExecutionStatus.SUCCEEDED, content=content,
    )


def task(run_id, role, *upstream):
    return envelope(run_id, AgentRole.COORDINATOR, TaskInput(
        task=WorkflowTask(task_id=uuid4(), agent=role, objective="Evaluate candidate claim"),
        upstream=upstream,
    ))


async def evaluate(case, repository, settings, *, reverse=False, fault=None):
    started = perf_counter()
    files = list(case["documents"].items())
    if reverse:
        files.reverse()
    documents = tuple(DocumentIngestor().parse(name, text.encode()) for name, text in files)
    ids = repository.ingest(documents)
    run = RunRecord(
        run_id=uuid4(), request=RunRequest(question=case["question"], source_ids=ids),
        model=settings.model_metadata(), started_at=datetime.now(UTC), status=ExecutionStatus.RUNNING,
    )
    repository.start(run)
    by_name = {doc.source.document_name: doc.passages[0].ref for doc in documents}
    names = {ref: name for name, ref in by_name.items()}
    citations = tuple(
        by_name.get(name, EvidenceRef(source_id=name, passage_id="missing"))
        for name in case["citations"]
    )
    claim = Claim(claim_id=uuid4(), statement=case["claim"], evidence_refs=citations)
    retrieved = RetrievalResult(passages=tuple(
        RetrievedPassage(
            passage=doc.passages[0], document_name=doc.source.document_name,
            retrieval_timestamp=datetime.now(UTC), retrieved_by_agent=AgentRole.RETRIEVAL,
        ) for doc in documents
    ))
    client = ModelClient(run.model, FaultBackend(fault) if fault else OfflineDocumentBackend())
    batch = await VerificationAgent(client, repository.resolve_for_run).run(task(
        run.run_id, AgentRole.VERIFICATION, envelope(run.run_id, AgentRole.RETRIEVAL, retrieved),
        envelope(run.run_id, AgentRole.ANALYSIS, AnalysisResult(claims=(claim,))),
    ))
    decision = await SynthesisAgent().run(task(
        run.run_id, AgentRole.SYNTHESIS, envelope(run.run_id, AgentRole.VERIFICATION, batch),
    ))
    verdict = batch.results[0]
    resolved = verdict.citations.resolved_refs
    exact = sum(
        repository.resolve_for_run(run.run_id, item.passage.ref) == item.passage
        for item in retrieved.passages if item.passage.ref in resolved
    )
    return {
        "id": case["id"], "expected": case["label"], "predicted": verdict.assessment.label,
        "expected_release": case["label"] == "SUPPORTED",
        "released": bool(decision.synthesis.finding_claim_ids),
        "mechanical_only": bool(resolved) and not verdict.citations.issues,
        "ungated": True, "citations": len(citations), "resolved": len(resolved), "exact_links": exact,
        "gold_support": case["support"], "gold_oppose": case["oppose"],
        "support": sorted(names[ref] for ref in verdict.assessment.supporting_refs),
        "oppose": sorted(names[ref] for ref in verdict.assessment.contradicting_refs),
        "method": verdict.method, "reason": verdict.assessment.explanation,
        "latency_ms": (perf_counter() - started) * 1000,
    }


def signature(row):
    return tuple(row[key] for key in ("predicted", "released", "resolved", "support", "oppose"))


async def evaluate_workflow(case, repository, settings, *, reverse=False, distractor=False):
    files = list(case["documents"].items())
    if reverse:
        files.reverse()
    if distractor:
        files.append(("distractor.txt", "A violin has four strings."))
    documents = tuple(DocumentIngestor().parse(name, text.encode()) for name, text in files)
    started = perf_counter()
    report = await run_parsed(settings, repository, case["question"], documents)
    claims = {
        claim.claim_id: claim.statement for message in report.messages
        if isinstance(message.content, AnalysisResult) for claim in message.content.claims
    }
    dispositions = report.result.decision.considered if report.result else ()
    return {
        "id": case["id"], "status": report.run.status, "steps": report.steps,
        "messages": len(report.messages), "reopened_equal": repository.inspect(report.run.run_id) == report,
        "retrieved_documents": sorted({
            item.document_name for message in report.messages
            if isinstance(message.content, RetrievalResult) for item in message.content.passages
        }),
        "claims": sorted(
            (claims[item.verification.claim_id], item.verification.assessment.label, item.eligible)
            for item in dispositions
        ),
        "released": sum(item.eligible for item in dispositions),
        "latency_ms": (perf_counter() - started) * 1000,
    }


def workflow_signature(row):
    return tuple(row[key] for key in ("status", "retrieved_documents", "claims", "released"))


async def benchmark(dataset, repeats):
    settings = Settings(provider="offline", model="deterministic-v1", model_timeout_seconds=1,
                        max_output_tokens=512, _env_file=None)
    cases = dataset["cases"]
    with TemporaryDirectory() as folder:
        repository = EvidenceRepository(Path(folder) / "bench.sqlite")
        primary = [await evaluate(case, repository, settings) for case in cases]
        repeated = [
            [await evaluate(case, repository, settings) for case in cases] for _ in range(repeats - 1)
        ]
        reversed_rows = [await evaluate(case, repository, settings, reverse=True) for case in cases]
        faults = {
            fault: await evaluate(cases[0], repository, settings, fault=fault)
            for fault in ("failure", "timeout", "malformed")
        }
        workflow_runs = {
            name: [await evaluate_workflow(case, repository, settings, **options) for case in cases]
            for name, options in (
                ("primary", {}), ("repeat", {}), ("reversed", {"reverse": True}),
                ("distractor", {"distractor": True}),
            )
        }
    return {
        "dataset_version": dataset["version"], "annotation_status": dataset["annotation_status"],
        "environment": {"python": platform.python_version(), "platform": platform.platform(),
                        "sqlite": sqlite3.sqlite_version},
        "model": settings.model_metadata().model_dump(), "tokens": None, "estimated_api_cost": None,
        "metrics": score(primary),
        "release": {key: release_metrics(primary, key) for key in ("released", "mechanical_only", "ungated")},
        "robustness": {
            "repeated_case_comparisons": len(cases) * (repeats - 1),
            "repeat_disagreements": sum(
                signature(a) != signature(b) for rows in repeated for a, b in zip(primary, rows, strict=True)
            ),
            "reverse_order_disagreements": sum(
                signature(a) != signature(b) for a, b in zip(primary, reversed_rows, strict=True)
            ),
            "latency_ms_per_pass": [mean(row["latency_ms"] for row in rows) for rows in [primary, *repeated, reversed_rows]],
            "faults": faults,
        },
        "cases": primary, "repeated": repeated, "reversed": reversed_rows,
        "workflow_runs": workflow_runs,
        "workflow_comparison": {
            name: {
                "disagreements": sum(
                    workflow_signature(a) != workflow_signature(b)
                    for a, b in zip(workflow_runs["primary"], rows, strict=True)
                ),
                "completion_rate": mean(row["status"] in ("succeeded", "partial") for row in rows),
                "mean_latency_ms": mean(row["latency_ms"] for row in rows),
                "reports_reopened_equal": sum(row["reopened_equal"] for row in rows),
            }
            for name, rows in workflow_runs.items()
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Run the deterministic MAEDS benchmark")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 2 <= args.repeats <= 20:
        parser.error("--repeats must be between 2 and 20")
    data = DATASET.read_bytes()
    result = asyncio.run(benchmark(json.loads(data), args.repeats))
    result["dataset_sha256"] = hashlib.sha256(data).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
