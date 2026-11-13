from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.models.contracts import AgentMessage, AgentRole, SynthesisResult, VerificationLabel
from app.models.workflow import (
    ClaimDisposition, DecisionResult, TaskInput, VerificationBatch, WorkflowDecision,
)


def dispositions(message: AgentMessage[TaskInput]) -> tuple[ClaimDisposition, ...]:
    records = []
    for upstream in message.content.upstream:
        if not isinstance(upstream.content, VerificationBatch):
            continue
        for item in upstream.content.results:
            assessment = item.assessment
            if item.citations.issues or not item.citations.resolved_refs:
                reason = "Citation validation did not fully pass."
            elif assessment.label != VerificationLabel.SUPPORTED:
                reason = f"Semantic verdict is {assessment.label}."
            elif (
                not assessment.supporting_refs
                or assessment.contradicting_refs
                or not set(assessment.supporting_refs) & set(item.citations.resolved_refs)
            ):
                reason = "No cited passage was confirmed as supporting evidence."
            else:
                reason = "All citations resolved and a cited passage supports the claim."
                records.append(ClaimDisposition(verification=item, eligible=True, reason=reason))
                continue
            records.append(ClaimDisposition(verification=item, eligible=False, reason=reason))
    return tuple(records)


def assemble_decision(
    message: AgentMessage[TaskInput], decision_id: UUID, timestamp: datetime,
) -> DecisionResult:
    considered = dispositions(message)
    findings = tuple(item.verification.claim_id for item in considered if item.eligible)
    unresolved = tuple(item.verification.claim_id for item in considered if not item.eligible)
    if findings:
        outcome = "mixed_findings" if unresolved else "supported_findings"
    elif considered:
        outcome = "no_eligible_claims"
    else:
        outcome = "no_candidate_claims"
    refs = tuple(dict.fromkeys(
        ref for item in considered
        for ref in (*item.verification.assessment.supporting_refs,
                    *item.verification.assessment.contradicting_refs)
    ))
    return DecisionResult(
        decision=WorkflowDecision(
            decision_id=decision_id, run_id=message.run_id, agent=AgentRole.SYNTHESIS,
            action="publish_supported_findings" if findings else "withhold_recommendation",
            outcome=outcome, timestamp=timestamp, evidence_refs=refs, abstained=True,
            considered=considered,
            input_message_ids=tuple(item.message_id for item in message.content.upstream),
        ),
        synthesis=SynthesisResult(
            decision_id=decision_id, finding_claim_ids=findings, unresolved_claim_ids=unresolved,
        ),
    )


class SynthesisAgent:
    async def run(self, message: AgentMessage[TaskInput]) -> DecisionResult:
        return assemble_decision(message, uuid4(), datetime.now(UTC))
