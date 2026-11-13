import asyncio
from uuid import uuid4

import pytest

from app.agents.analysis import AnalysisAgent
from app.agents.coordinator import CoordinatorAgent
from app.agents.retrieval import RetrievalAgent
from app.agents.synthesis import SynthesisAgent
from app.agents.verification import VerificationAgent
from app.config import Settings
from app.models.contracts import AgentRole, EvidenceRef, ExecutionStatus, MessageType, Passage, RunRequest
from app.models.workflow import (
    FixturePassage, StatusCode, TaskInput, TaskStatus, VerificationBatch, WorkflowReport,
    WorkflowRequest,
)
from app.orchestrator.demo import run_demo
from app.orchestrator.workflow import WorkflowLimits, WorkflowRunner
from app.services.model import build_model_client


def fixture_workflow():
    return WorkflowRequest(
        request=RunRequest(question="Compare the pilots.", source_ids=("a", "b")),
        corpus=tuple(
            FixturePassage(
                document_name=source,
                passage=Passage(
                    ref=EvidenceRef(source_id=source, passage_id="budget"),
                    text="Budget", start=0, end=6,
                ),
            )
            for source in ("a", "b")
        ),
    )


def setup_runner(workflow, *, overrides=None, coordinator=None, **limits):
    client = build_model_client(Settings(), {"select_passages": {"passage_indexes": [0, 1]}})
    handlers = {
        AgentRole.RETRIEVAL: RetrievalAgent(workflow.corpus).run,
        AgentRole.ANALYSIS: AnalysisAgent(client).run,
        AgentRole.VERIFICATION: VerificationAgent().run,
        AgentRole.SYNTHESIS: SynthesisAgent().run,
    }
    handlers.update(overrides or {})
    return WorkflowRunner(
        client, coordinator or CoordinatorAgent().plan, handlers, WorkflowLimits(**limits),
    )


def task_statuses(report):
    return [message.content for message in report.messages if isinstance(message.content, TaskStatus)]


def test_all_five_roles_exchange_round_trippable_messages():
    report = asyncio.run(run_demo(Settings()))
    assert report.steps == 6
    assert report.run.status == ExecutionStatus.SUCCEEDED
    assert report.run.model.provider == "offline"
    assert report.result is not None
    assert len(report.result.synthesis.finding_claim_ids) == 2
    assert not report.result.synthesis.unresolved_claim_ids
    results = [message for message in report.messages if message.message_type == MessageType.RESULT]
    assert {message.sender_agent for message in results} == set(AgentRole)
    assert all(message.recipient_agent == AgentRole.COORDINATOR for message in results)
    assert all(message.parent_message_id for message in results)
    assert WorkflowReport.model_validate_json(report.model_dump_json()) == report
    verification = next(m.content for m in results if isinstance(m.content, VerificationBatch))
    assert tuple(item.citations.resolved_refs[0].source_id for item in verification.results) == report.run.request.source_ids
    assert {item.assessment.label for item in verification.results} == {"SUPPORTED"}


@pytest.mark.parametrize("parallelism", [1, 2])
def test_execution_respects_dependencies_and_parallel_limit(parallelism):
    async def scenario():
        workflow = fixture_workflow()
        entered = 0
        completed = 0
        rendezvous = asyncio.Event()
        observed = []
        retrieval = RetrievalAgent(workflow.corpus)

        async def retrieve(message):
            nonlocal entered, completed
            entered += 1
            observed.append(entered - completed)
            if entered == 2:
                rendezvous.set()
            if parallelism == 2:
                await asyncio.wait_for(rendezvous.wait(), timeout=1)
            result = await retrieval.run(message)
            completed += 1
            return result

        runner = setup_runner(
            workflow, overrides={AgentRole.RETRIEVAL: retrieve}, max_parallel=parallelism,
        )
        report = await runner.run(workflow)
        assert report.result is not None
        assert max(observed) == parallelism
        seen = set()
        for message in report.messages:
            if isinstance(message.content, TaskInput):
                assert {item.task_id for item in message.content.upstream} == set(
                    message.content.task.dependency_ids
                )
                assert all(item.message_id in seen for item in message.content.upstream)
            seen.add(message.message_id)

    asyncio.run(scenario())


def test_empty_evidence_routes_around_analysis():
    report = asyncio.run(run_demo(Settings(), empty=True))
    assert report.run.status == ExecutionStatus.SUCCEEDED
    assert report.steps == 5
    assert [status.code for status in task_statuses(report)] == [StatusCode.NO_EVIDENCE]
    assert report.result is not None
    assert report.result.synthesis.unresolved_claim_ids == ()


@pytest.mark.parametrize(
    ("fault", "code", "recovers"),
    [
        ("failure", StatusCode.FAILURE, True),
        ("malformed", StatusCode.MALFORMED, False),
        ("timeout", StatusCode.TIMEOUT, False),
    ],
)
def test_fault_retry_and_dependency_failure(fault, code, recovers):
    workflow = fixture_workflow()
    retrieval = RetrievalAgent(workflow.corpus)
    attempts = 0
    cancellations = 0

    async def retrieve(message):
        nonlocal attempts, cancellations
        if message.content.task.source_id == "b":
            return await retrieval.run(message)
        attempts += 1
        if fault == "failure" and attempts == 1:
            raise RuntimeError("injected")
        if fault == "malformed":
            return {"passages": ["invalid"]}
        if fault == "timeout":
            try:
                await asyncio.Future()
            finally:
                cancellations += 1
        return await retrieval.run(message)

    runner = setup_runner(
        workflow, overrides={AgentRole.RETRIEVAL: retrieve}, attempt_timeout_seconds=0.03,
    )
    report = asyncio.run(runner.run(workflow))
    assert attempts == 2
    assert cancellations == (2 if fault == "timeout" else 0)
    assert [item.attempt for item in task_statuses(report) if item.code == code] == (
        [1] if recovers else [1, 2]
    )
    assert report.run.status == (ExecutionStatus.PARTIAL if recovers else ExecutionStatus.FAILED)
    assert (report.result is not None) == recovers
    if not recovers:
        assert len([item for item in task_statuses(report) if item.code == StatusCode.DEPENDENCY_FAILED]) == 3


@pytest.mark.parametrize("defect", ["cycle", "unknown_role", "missing_dependency", "duplicate_id", "source"])
def test_rejects_invalid_plan_before_specialist_dispatch(defect):
    workflow = fixture_workflow()

    async def coordinator(message):
        plan = (await CoordinatorAgent().plan(message)).model_dump()
        first, second, analysis, *_ = plan["tasks"]
        if defect == "cycle":
            first["dependency_ids"] = (analysis["task_id"],)
        elif defect == "unknown_role":
            first["agent"] = "unknown"
        elif defect == "missing_dependency":
            analysis["dependency_ids"] = (uuid4(),)
        elif defect == "source":
            first["source_id"] = "outside-scope"
        else:
            second["task_id"] = first["task_id"]
        return plan

    runner = setup_runner(workflow, coordinator=coordinator, max_retries=0)
    report = asyncio.run(runner.run(workflow))
    assert report.run.status == ExecutionStatus.FAILED
    assert report.steps == 1
    assert not any(isinstance(message.content, TaskInput) for message in report.messages)
    expected = StatusCode.MALFORMED if defect == "unknown_role" else StatusCode.INVALID_PLAN
    assert [item.code for item in task_statuses(report)] == [expected]


@pytest.mark.parametrize("budget", [1, 2, 5])
def test_step_budget_counts_attempts_and_terminates(budget):
    workflow = fixture_workflow()
    runner = setup_runner(workflow, max_steps=budget)
    report = asyncio.run(runner.run(workflow))
    assert report.steps == budget
    assert report.run.status == ExecutionStatus.FAILED
    assert report.result is None
    assert StatusCode.STEP_LIMIT in {item.code for item in task_statuses(report)}


def test_release_rejects_unverified_finding_ids():
    workflow = fixture_workflow()

    async def synthesize(message):
        result = (await SynthesisAgent().run(message)).model_dump()
        result["synthesis"]["finding_claim_ids"] = (uuid4(),)
        return result

    runner = setup_runner(
        workflow, overrides={AgentRole.SYNTHESIS: synthesize}, max_retries=0,
    )
    report = asyncio.run(runner.run(workflow))
    assert report.run.status == ExecutionStatus.FAILED
    assert report.result is None
    assert task_statuses(report)[-1].code == StatusCode.MALFORMED
