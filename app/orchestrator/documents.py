import asyncio
import json
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from app.agents.analysis import AnalysisAgent
from app.agents.coordinator import CoordinatorAgent
from app.agents.retrieval import RetrievalAgent
from app.agents.synthesis import SynthesisAgent
from app.agents.verification import VerificationAgent
from app.config import Settings
from app.models.contracts import AgentMessage, AgentRole, RunRecord, RunRequest
from app.models.workflow import TaskInput, WorkflowReport, WorkflowRequest
from app.orchestrator.workflow import WorkflowRunner
from app.services.ingestion import DocumentIngestor, IngestionError, ParsedDocument
from app.services.model import ModelClient, ModelRequest, build_model_client
from app.services.offline_verification import assess_offline
from app.services.repository import EvidenceRepository, RepositoryError


class OfflineDocumentBackend:
    async def generate(self, request: ModelRequest, schema: type[BaseModel]) -> object:
        data = json.loads(request.input_text)
        if request.operation == "verify_claim":
            return assess_offline(data["claim"], data["passages"])
        return {"passage_indexes": list(range(min(len(data["passages"]), 16)))}


async def run_documents(
    settings: Settings, repository: EvidenceRepository, question: str, paths: tuple[Path, ...],
) -> WorkflowReport:
    if not 1 <= len(paths) <= 16:
        raise IngestionError("Supply between 1 and 16 files")
    if not question.strip() or len(question) > 2_000:
        raise IngestionError("Supply a question of up to 2,000 characters")
    ingestor = DocumentIngestor()
    return await run_parsed(settings, repository, question, tuple(ingestor.read(path) for path in paths))


async def run_parsed(
    settings: Settings, repository: EvidenceRepository, question: str,
    documents: tuple[ParsedDocument, ...], *, on_start: Callable[[RunRecord], None] | None = None,
) -> WorkflowReport:
    if not 1 <= len(documents) <= 16 or not question.strip() or len(question) > 2_000:
        raise IngestionError("Supply 1 to 16 files and a question of up to 2,000 characters")
    source_ids = repository.ingest(documents)
    workflow = WorkflowRequest(request=RunRequest(question=question, source_ids=source_ids))
    client = (
        ModelClient(settings.model_metadata(), OfflineDocumentBackend())
        if settings.provider == "offline" else build_model_client(settings, {})
    )

    async def search(message: AgentMessage[TaskInput]):
        task = message.content.task
        if task.source_id is None:
            raise RepositoryError("Retrieval requires an assigned source")
        return await asyncio.to_thread(repository.search, message.run_id, task.source_id, task.objective)

    runner = WorkflowRunner(client, CoordinatorAgent().plan, {
        AgentRole.RETRIEVAL: RetrievalAgent(search=search).run,
        AgentRole.ANALYSIS: AnalysisAgent(client).run,
        AgentRole.VERIFICATION: VerificationAgent(client, repository.resolve_for_run).run,
        AgentRole.SYNTHESIS: SynthesisAgent().run,
    })
    started: RunRecord | None = None

    def start(record: RunRecord) -> None:
        nonlocal started
        repository.start(record)
        started = record
        if on_start is not None:
            on_start(record)

    try:
        report = await runner.run(workflow, on_start=start)
        repository.finish(report)
    except (Exception, asyncio.CancelledError) as exc:
        if started is not None:
            try:
                repository.fail(started)
            except RepositoryError:
                exc.add_note("Could not update the stored run to failed")
        raise
    return report
