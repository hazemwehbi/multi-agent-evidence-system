from enum import StrEnum
from typing import Annotated, Generic, Self, TypeVar
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field, StringConstraints, model_validator

from app.config import ModelMetadata

NonEmpty = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]


class Contract(BaseModel, extra="forbid", frozen=True):
    """Base class for data crossing application boundaries."""


class AgentRole(StrEnum):
    COORDINATOR = "coordinator"
    RETRIEVAL = "retrieval"
    ANALYSIS = "analysis"
    VERIFICATION = "verification"
    SYNTHESIS = "synthesis"


class ExecutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"
    INTERRUPTED = "interrupted"


class MessageType(StrEnum):
    TASK = "task"
    RESULT = "result"
    CRITIQUE = "critique"
    VERIFICATION = "verification"
    STATUS = "status"


class EvidenceRef(Contract):
    source_id: NonEmpty
    passage_id: NonEmpty


class SourceDocument(Contract):
    source_id: NonEmpty
    document_name: NonEmpty
    text: NonEmpty


class Passage(Contract):
    ref: EvidenceRef
    text: NonEmpty
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    section: NonEmpty | None = None
    page_number: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_span(self) -> Self:
        if self.end - self.start != len(self.text):
            raise ValueError("Passage text length must match its character span")
        return self


class RetrievedPassage(Contract):
    passage: Passage
    document_name: NonEmpty
    retrieval_timestamp: AwareDatetime
    retrieved_by_agent: AgentRole


class RunRequest(Contract):
    question: NonEmpty
    source_ids: tuple[NonEmpty, ...] = Field(min_length=1)


class RunRecord(Contract):
    run_id: UUID
    request: RunRequest
    model: ModelMetadata
    started_at: AwareDatetime
    status: ExecutionStatus


class Task(Contract):
    task_id: UUID
    agent: AgentRole
    objective: NonEmpty
    dependency_ids: tuple[UUID, ...] = ()


Payload = TypeVar("Payload", bound=Contract)


class AgentMessage(Contract, Generic[Payload]):
    message_id: UUID
    run_id: UUID
    task_id: UUID
    sender_agent: AgentRole
    recipient_agent: AgentRole
    message_type: MessageType
    content: Payload
    evidence_refs: tuple[EvidenceRef, ...] = ()
    parent_message_id: UUID | None = None
    timestamp: AwareDatetime
    execution_status: ExecutionStatus


class Claim(Contract):
    claim_id: UUID
    statement: NonEmpty
    evidence_refs: tuple[EvidenceRef, ...] = ()


class VerificationLabel(StrEnum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    CONFLICTING = "CONFLICTING"
    NOT_VERIFIABLE = "NOT_VERIFIABLE"


class CitationIssue(Contract):
    ref: EvidenceRef
    reason: NonEmpty


class CitationCheck(Contract):
    resolved_refs: tuple[EvidenceRef, ...] = ()
    issues: tuple[CitationIssue, ...] = ()


class SemanticAssessment(Contract):
    label: VerificationLabel
    explanation: NonEmpty
    supporting_refs: tuple[EvidenceRef, ...] = ()
    contradicting_refs: tuple[EvidenceRef, ...] = ()


class VerificationResult(Contract):
    claim_id: UUID
    citations: CitationCheck
    assessment: SemanticAssessment
    method: str = "legacy"
    model: ModelMetadata | None = None


class DecisionRecord(Contract):
    decision_id: UUID
    run_id: UUID
    agent: AgentRole
    action: NonEmpty
    outcome: NonEmpty
    timestamp: AwareDatetime
    evidence_refs: tuple[EvidenceRef, ...] = ()
    input_message_ids: tuple[UUID, ...] = ()
    alternatives: tuple[NonEmpty, ...] = ()


class SynthesisResult(Contract):
    """References decision and claim records in the current run."""

    decision_id: UUID
    finding_claim_ids: tuple[UUID, ...] = ()
    unresolved_claim_ids: tuple[UUID, ...] = ()
