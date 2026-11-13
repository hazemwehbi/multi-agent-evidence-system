from enum import StrEnum
from uuid import UUID

from typing import Literal, Self

from pydantic import Field, model_validator

from app.models.contracts import (
    AgentMessage, Claim, Contract, DecisionRecord, EvidenceRef, NonEmpty, Passage,
    RetrievedPassage, RunRecord, RunRequest, SynthesisResult, Task, VerificationResult,
)


class WorkflowTask(Task):
    source_id: NonEmpty | None = None


class Plan(Contract):
    tasks: tuple[WorkflowTask, ...] = Field(min_length=1, max_length=19)


class RetrievalResult(Contract):
    passages: tuple[RetrievedPassage, ...] = ()


class AnalysisResult(Contract):
    claims: tuple[Claim, ...] = ()


class VerificationBatch(Contract):
    results: tuple[VerificationResult, ...] = ()


class WorkflowDecision(DecisionRecord):
    action: Literal["withhold_recommendation", "publish_supported_findings"]
    outcome: Literal[
        "awaiting_semantic_verification", "no_candidate_claims", "no_eligible_claims",
        "supported_findings", "mixed_findings",
    ]
    abstained: bool = True
    considered: tuple["ClaimDisposition", ...] = ()


class ClaimDisposition(Contract):
    verification: VerificationResult
    eligible: bool
    reason: NonEmpty


class DecisionResult(Contract):
    decision: WorkflowDecision
    synthesis: SynthesisResult


StageResult = RetrievalResult | AnalysisResult | VerificationBatch | DecisionResult
ResultMessage = (
    AgentMessage[RetrievalResult] | AgentMessage[AnalysisResult]
    | AgentMessage[VerificationBatch] | AgentMessage[DecisionResult]
)


class TaskInput(Contract):
    task: WorkflowTask
    upstream: tuple[ResultMessage, ...] = ()


class FixturePassage(Contract):
    document_name: NonEmpty
    passage: Passage


class WorkflowRequest(Contract):
    request: RunRequest
    corpus: tuple[FixturePassage, ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        sources = self.request.source_ids
        if len(sources) > 16 or len(set(sources)) != len(sources):
            raise ValueError("Supply at most 16 unique source IDs")
        if len(self.request.question) > 2_000:
            raise ValueError("Question exceeds 2,000 characters")
        refs = tuple(item.passage.ref for item in self.corpus)
        if len(set(refs)) != len(refs) or any(ref.source_id not in sources for ref in refs):
            raise ValueError("Fixture references must be unique and within the request scope")
        if any(len(item.passage.text) > 2_000 for item in self.corpus):
            raise ValueError("Fixture passage exceeds 2,000 characters")
        return self

class StatusCode(StrEnum):
    FAILURE = "agent_failure"
    TIMEOUT = "timeout"
    MALFORMED = "malformed_response"
    INVALID_PLAN = "invalid_plan"
    NO_EVIDENCE = "no_evidence"
    DEPENDENCY_FAILED = "dependency_failed"
    STEP_LIMIT = "step_limit"


class TaskStatus(Contract):
    code: StatusCode
    attempt: int | None = None


TraceMessage = (
    AgentMessage[RunRequest] | AgentMessage[Plan] | AgentMessage[TaskInput]
    | ResultMessage | AgentMessage[TaskStatus]
)


class WorkflowReport(Contract):
    run: RunRecord
    steps: int
    messages: tuple[TraceMessage, ...]
    result: DecisionResult | None = None


def evidence_refs(result: StageResult) -> tuple[EvidenceRef, ...]:
    if isinstance(result, RetrievalResult):
        return tuple(item.passage.ref for item in result.passages)
    if isinstance(result, AnalysisResult):
        return tuple(dict.fromkeys(ref for claim in result.claims for ref in claim.evidence_refs))
    if isinstance(result, VerificationBatch):
        return tuple(dict.fromkeys(
            ref for item in result.results
            for ref in (*item.citations.resolved_refs, *item.assessment.supporting_refs,
                        *item.assessment.contradicting_refs)
        ))
    return result.decision.evidence_refs
