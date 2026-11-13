import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.agents.synthesis import SynthesisAgent
from app.agents.verification import VerificationAgent
from app.config import Settings
from app.models.contracts import (
    AgentMessage, AgentRole, Claim, EvidenceRef, ExecutionStatus, MessageType,
    RetrievedPassage, RunRecord, RunRequest, VerificationLabel,
)
from app.models.workflow import AnalysisResult, RetrievalResult, TaskInput, WorkflowTask
from app.orchestrator.documents import OfflineDocumentBackend
from app.services.ingestion import DocumentIngestor
from app.services.model import ModelClient, OfflineBackend
from app.services.repository import EvidenceRepository


@pytest.mark.parametrize(("claim_text", "texts", "expected", "supports", "opposes", "eligible"), [
    ("Pilot budget is 20.", ("Pilot budget is 20.", "Pilot budget is 20."), "SUPPORTED", 2, 0, True),
    ("Pilot budget is 20 and opens in May.", ("Pilot budget is 20.",), "PARTIALLY_SUPPORTED", 1, 0, False),
    ("Pilot opens in May.", ("Pilot budget is 20.",), "UNSUPPORTED", 0, 0, False),
    ("Pilot budget is 20.", ("Pilot budget is 20.", "Pilot budget is 24."), "CONFLICTING", 1, 1, False),
    ("Pilot budget is 20.", (), "NOT_VERIFIABLE", 0, 0, False),
    ("Pilot budget is 20.", ("Pilot budget is 20.",), "NOT_VERIFIABLE", 0, 0, False),
    ("Pilot budget is 20.", ("Pilot budget is 20.", "Unrelated."), "SUPPORTED", 1, 0, False),
])
def test_source_backed_verification_and_release(
    tmp_path, claim_text, texts, expected, supports, opposes, eligible,
):
    bad_citation = (expected == "NOT_VERIFIABLE" and bool(texts)) or texts[-1:] == ("Unrelated.",)
    repository = EvidenceRepository(tmp_path / "evidence.sqlite")
    parser = DocumentIngestor()
    docs = tuple(parser.parse(f"{i}.txt", text.encode()) for i, text in enumerate(texts or ("empty",)))
    sources = repository.ingest(docs)
    settings = Settings()
    record = RunRecord(
        run_id=uuid4(), request=RunRequest(question="Budget?", source_ids=sources),
        started_at=datetime.now(UTC), status=ExecutionStatus.RUNNING, model=settings.model_metadata(),
    )
    repository.start(record)
    passages = tuple(doc.passages[0] for doc in docs) if texts else ()
    refs = tuple(p.ref for p in passages)
    if bad_citation:
        refs = (() if expected == "NOT_VERIFIABLE" else refs[:1]) + (
            EvidenceRef(source_id=sources[0], passage_id="bad"),
        )
    claim = Claim(claim_id=uuid4(), statement=claim_text, evidence_refs=refs)

    def message(payload, role):
        return AgentMessage[type(payload)](
            message_id=uuid4(), run_id=record.run_id, task_id=uuid4(),
            sender_agent=role, recipient_agent=AgentRole.COORDINATOR,
            message_type=MessageType.RESULT, timestamp=datetime.now(UTC),
            execution_status=ExecutionStatus.SUCCEEDED, content=payload,
        )

    def task(role, *upstream):
        return message(TaskInput(
            task=WorkflowTask(task_id=uuid4(), agent=role, objective="Budget"),
            upstream=upstream,
        ), role)

    retrieved = RetrievalResult(passages=tuple(
        RetrievedPassage(
            passage=p, document_name=doc.source.document_name, retrieval_timestamp=datetime.now(UTC),
            retrieved_by_agent=AgentRole.RETRIEVAL,
        )
        for doc, p in zip(docs, passages)
    ))
    verification_task = task(
        AgentRole.VERIFICATION, message(retrieved, AgentRole.RETRIEVAL),
        message(AnalysisResult(claims=(claim,)), AgentRole.ANALYSIS),
    )
    client = ModelClient(settings.model_metadata(), OfflineDocumentBackend())
    batch = asyncio.run(VerificationAgent(client, repository.resolve_for_run).run(verification_task))
    item = batch.results[0]
    assert item.assessment.label == expected
    assert len(item.assessment.supporting_refs) == supports
    assert len(item.assessment.contradicting_refs) == opposes
    assert bool(item.citations.issues) == bad_citation
    if expected == "UNSUPPORTED":
        assert item.citations.resolved_refs == refs
    decision = asyncio.run(SynthesisAgent().run(task(
        AgentRole.SYNTHESIS, message(batch, AgentRole.VERIFICATION),
    )))
    assert decision.decision.considered[0].verification == item
    assert decision.decision.considered[0].eligible is eligible
    assert decision.decision.abstained
    assert decision.synthesis.finding_claim_ids == ((claim.claim_id,) if eligible else ())
    if eligible:
        assert item.model == settings.model_metadata()
        assert item.method == "offline_rules_v2"

    malformed = ModelClient(settings.model_metadata(), OfflineBackend({
        "verify_claim": {"label": "SUPPORTED", "explanation": "Bad index",
                         "supporting_indexes": [900], "contradicting_indexes": []},
    }))
    if item.citations.resolved_refs:
        failed = asyncio.run(VerificationAgent(malformed, repository.resolve_for_run).run(verification_task))
        assert failed.results[0].assessment.label == VerificationLabel.NOT_VERIFIABLE
        assert "invalid assessment" in failed.results[0].assessment.explanation
