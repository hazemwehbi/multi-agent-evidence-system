import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import Field, ValidationError

from app.agents.synthesis import assemble_decision
from app.models.contracts import (
    AgentMessage, AgentRole, Contract, EvidenceRef, ExecutionStatus, MessageType, RunRecord, RunRequest,
)
from app.models.workflow import (
    AnalysisResult, DecisionResult, Plan, ResultMessage, RetrievalResult, StageResult,
    StatusCode, TaskInput, TaskStatus, TraceMessage, VerificationBatch, WorkflowReport,
    WorkflowRequest, WorkflowTask, evidence_refs,
)
from app.services.model import InvalidModelOutput, ModelClient, ModelTimeout

Coordinator = Callable[[AgentMessage[RunRequest]], Awaitable[object]]
Handler = Callable[[AgentMessage[TaskInput]], Awaitable[object]]
RESULT_TYPES = {
    AgentRole.RETRIEVAL: RetrievalResult,
    AgentRole.ANALYSIS: AnalysisResult,
    AgentRole.VERIFICATION: VerificationBatch,
    AgentRole.SYNTHESIS: DecisionResult,
}


class WorkflowLimits(Contract):
    max_steps: int = Field(default=32, ge=1, le=256)
    max_retries: int = Field(default=1, ge=0, le=4)
    max_parallel: int = Field(default=4, ge=1, le=16)
    attempt_timeout_seconds: float = Field(default=20, gt=0, le=120)


def validate_plan(plan: Plan, request: RunRequest) -> None:
    """Validate the dependency layers and source assignments before dispatch."""
    tasks = plan.tasks
    if len({task.task_id for task in tasks}) != len(tasks):
        raise ValueError("Duplicate task IDs")
    grouped = {role: [task for task in tasks if task.agent == role] for role in RESULT_TYPES}
    retrieval = grouped[AgentRole.RETRIEVAL]
    if (
        len(retrieval) != len(request.source_ids)
        or {task.source_id for task in retrieval} != set(request.source_ids)
        or any(task.dependency_ids for task in retrieval)
        or len(tasks) != len(retrieval) + 3
    ):
        raise ValueError("Invalid retrieval layer")

    retrieval_ids = {task.task_id for task in retrieval}
    expected = retrieval_ids
    for role in (AgentRole.ANALYSIS, AgentRole.VERIFICATION, AgentRole.SYNTHESIS):
        layer = grouped[role]
        if len(layer) != 1:
            raise ValueError("Invalid stage count")
        task = layer[0]
        if (
            task.source_id is not None
            or set(task.dependency_ids) != expected
            or len(task.dependency_ids) != len(expected)
        ):
            raise ValueError("Invalid stage dependencies")
        expected = {task.task_id}
        if role == AgentRole.ANALYSIS:
            expected |= retrieval_ids


class WorkflowRunner:
    def __init__(
        self, client: ModelClient, coordinator: Coordinator,
        handlers: dict[AgentRole, Handler], limits: WorkflowLimits | None = None,
    ) -> None:
        if set(handlers) != set(RESULT_TYPES):
            raise ValueError("Register exactly the four specialist roles")
        self._client = client
        self._coordinator = coordinator
        self._handlers = dict(handlers)
        self._limits = limits or WorkflowLimits()

    async def run(
        self, workflow: WorkflowRequest, *, on_start: Callable[[RunRecord], None] | None = None,
    ) -> WorkflowReport:
        execution = _Execution(workflow.request, self._client)
        if on_start is not None:
            on_start(execution.record)
        kickoff = execution.send(
            workflow.request, task_id=uuid4(), sender=AgentRole.COORDINATOR,
            recipient=AgentRole.COORDINATOR, kind=MessageType.TASK,
            status=ExecutionStatus.RUNNING,
        )
        plan = None
        for attempt in range(1, self._limits.max_retries + 2):
            if execution.steps == self._limits.max_steps:
                execution.status(kickoff, StatusCode.STEP_LIMIT)
                break
            execution.steps += 1
            output, error = await self._invoke(self._coordinator, kickoff, Plan)
            if isinstance(output, Plan):
                try:
                    validate_plan(output, workflow.request)
                except ValueError:
                    execution.status(kickoff, StatusCode.INVALID_PLAN, attempt=attempt)
                    break
                plan = output
                break
            execution.status(kickoff, error or StatusCode.MALFORMED, attempt=attempt)
        if plan is None:
            return execution.report(None)

        plan_message = execution.send(
            plan, task_id=kickoff.task_id, sender=AgentRole.COORDINATOR,
            recipient=AgentRole.COORDINATOR, kind=MessageType.RESULT,
            status=ExecutionStatus.SUCCEEDED, parent=kickoff.message_id,
        )
        pending = {task.task_id: task for task in plan.tasks}
        results: dict[UUID, ResultMessage] = {}
        terminal: dict[UUID, ExecutionStatus] = {}
        attempts: dict[UUID, int] = {}
        decision = None
        while pending:
            ready = [
                task for task in pending.values()
                if all(dep in terminal for dep in task.dependency_ids)
            ]
            batch: list[tuple[WorkflowTask, AgentMessage[TaskInput]]] = []
            for task in ready:
                upstream = tuple(results[dep] for dep in task.dependency_ids if dep in results)
                message = execution.send(
                    TaskInput(task=task, upstream=upstream), task_id=task.task_id,
                    sender=AgentRole.COORDINATOR, recipient=task.agent, kind=MessageType.TASK,
                    status=ExecutionStatus.PENDING, parent=plan_message.message_id,
                    refs=tuple(dict.fromkeys(ref for item in upstream for ref in item.evidence_refs)),
                )
                code = self._skip_reason(task, upstream, terminal, execution.steps)
                if code is not None:
                    execution.status(message, code, status=ExecutionStatus.SKIPPED)
                    terminal[task.task_id] = (
                        ExecutionStatus.SKIPPED if code == StatusCode.NO_EVIDENCE
                        else ExecutionStatus.FAILED
                    )
                    del pending[task.task_id]
                    continue
                attempts[task.task_id] = attempts.get(task.task_id, 0) + 1
                execution.steps += 1
                batch.append((task, message))
                if len(batch) == self._limits.max_parallel:
                    break

            outcomes = await asyncio.gather(*(
                self._invoke(self._handlers[task.agent], message, RESULT_TYPES[task.agent])
                for task, message in batch
            ))
            for (task, message), (output, error) in zip(batch, outcomes, strict=True):
                if isinstance(output, VerificationBatch) and not self._valid_verification(output, message):
                    output, error = None, StatusCode.MALFORMED
                if isinstance(output, DecisionResult) and not self._valid_decision(output, message):
                    output, error = None, StatusCode.MALFORMED
                if output is None:
                    execution.status(
                        message, error or StatusCode.MALFORMED, attempt=attempts[task.task_id],
                    )
                    if attempts[task.task_id] <= self._limits.max_retries:
                        continue
                    terminal[task.task_id] = ExecutionStatus.FAILED
                else:
                    results[task.task_id] = execution.send(
                        output, task_id=task.task_id, sender=task.agent,
                        recipient=AgentRole.COORDINATOR, kind=MessageType.RESULT,
                        status=ExecutionStatus.SUCCEEDED, parent=message.message_id,
                        refs=evidence_refs(output),
                    )
                    terminal[task.task_id] = ExecutionStatus.SUCCEEDED
                    if isinstance(output, DecisionResult):
                        decision = output
                del pending[task.task_id]
        return execution.report(decision)

    @staticmethod
    def _valid_verification(batch: VerificationBatch, message: AgentMessage[TaskInput]) -> bool:
        claims = [
            claim for upstream in message.content.upstream
            if isinstance(upstream.content, AnalysisResult) for claim in upstream.content.claims
        ]
        retrieved = {
            item.passage.ref for upstream in message.content.upstream
            if isinstance(upstream.content, RetrievalResult) for item in upstream.content.passages
        }
        if len(batch.results) != len(claims):
            return False
        for item, claim in zip(batch.results, claims, strict=True):
            resolved = set(item.citations.resolved_refs)
            issues = {issue.ref for issue in item.citations.issues}
            assessed = set(item.assessment.supporting_refs) | set(item.assessment.contradicting_refs)
            if (
                item.claim_id != claim.claim_id or resolved & issues
                or resolved | issues != set(claim.evidence_refs)
                or not (resolved | assessed) <= retrieved
            ):
                return False
        return True

    @staticmethod
    def _valid_decision(result: DecisionResult, message: AgentMessage[TaskInput]) -> bool:
        expected = assemble_decision(message, result.decision.decision_id, result.decision.timestamp)
        return result == expected

    def _skip_reason(
        self, task: WorkflowTask, upstream: tuple[ResultMessage, ...],
        terminal: dict[UUID, ExecutionStatus], steps: int,
    ) -> StatusCode | None:
        if steps == self._limits.max_steps:
            return StatusCode.STEP_LIMIT
        if any(terminal[dep] == ExecutionStatus.FAILED for dep in task.dependency_ids):
            return StatusCode.DEPENDENCY_FAILED
        if task.agent == AgentRole.ANALYSIS and not any(
            isinstance(item.content, RetrievalResult) and item.content.passages
            for item in upstream
        ):
            return StatusCode.NO_EVIDENCE
        # Verification handles a deliberately skipped analysis as an empty batch.
        if task.agent == AgentRole.SYNTHESIS and not upstream:
            return StatusCode.DEPENDENCY_FAILED
        return None

    async def _invoke(
        self, handler: Callable[..., Awaitable[object]], message: AgentMessage,
        schema: type[Contract],
    ) -> tuple[Plan | StageResult | None, StatusCode | None]:
        try:
            async with asyncio.timeout(self._limits.attempt_timeout_seconds):
                response = await handler(message)
            # Validate field values even if a faulty handler used model_construct().
            if isinstance(response, Contract):
                response = response.model_dump(warnings=False)
            return schema.model_validate(response), None
        except (TimeoutError, ModelTimeout):
            return None, StatusCode.TIMEOUT
        except (ValidationError, InvalidModelOutput):
            return None, StatusCode.MALFORMED
        except Exception:
            return None, StatusCode.FAILURE


class _Execution:
    def __init__(self, request: RunRequest, client: ModelClient) -> None:
        self.record = RunRecord(
            run_id=uuid4(), request=request, model=client.metadata,
            started_at=datetime.now(UTC), status=ExecutionStatus.RUNNING,
        )
        self.steps = 0
        self.messages: list[TraceMessage] = []

    def send(
        self, payload: Contract, *, task_id: UUID, sender: AgentRole, recipient: AgentRole,
        kind: MessageType, status: ExecutionStatus, parent: UUID | None = None,
        refs: tuple[EvidenceRef, ...] = (),
    ) -> AgentMessage:
        message = AgentMessage[type(payload)](
            message_id=uuid4(), run_id=self.record.run_id, task_id=task_id,
            sender_agent=sender, recipient_agent=recipient, message_type=kind,
            content=payload, timestamp=datetime.now(UTC), execution_status=status,
            parent_message_id=parent, evidence_refs=refs,
        )
        self.messages.append(message)
        return message

    def status(
        self, message: AgentMessage, code: StatusCode, *, attempt: int | None = None,
        status: ExecutionStatus = ExecutionStatus.FAILED,
    ) -> None:
        self.send(
            TaskStatus(code=code, attempt=attempt), task_id=message.task_id,
            sender=AgentRole.COORDINATOR, recipient=AgentRole.COORDINATOR,
            kind=MessageType.STATUS, status=status, parent=message.message_id,
        )

    def report(self, decision: DecisionResult | None) -> WorkflowReport:
        status = ExecutionStatus.FAILED
        if decision is not None:
            status = (
                ExecutionStatus.PARTIAL if decision.synthesis.unresolved_claim_ids
                else ExecutionStatus.SUCCEEDED
            )
        return WorkflowReport(
            run=self.record.model_copy(update={"status": status}),
            steps=self.steps, messages=tuple(self.messages), result=decision,
        )
