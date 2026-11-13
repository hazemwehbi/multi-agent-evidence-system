from datetime import UTC, datetime
from collections.abc import Awaitable, Callable

from app.models.contracts import AgentMessage, AgentRole, Passage, RetrievedPassage
from app.models.workflow import FixturePassage, RetrievalResult, TaskInput

Search = Callable[[AgentMessage[TaskInput]], Awaitable[tuple[tuple[str, Passage], ...]]]


class RetrievalAgent:
    def __init__(self, corpus: tuple[FixturePassage, ...] = (), *, search: Search | None = None) -> None:
        self._corpus = corpus
        self._search = search

    async def run(self, message: AgentMessage[TaskInput]) -> RetrievalResult:
        passages = await self._search(message) if self._search is not None else tuple(
            (item.document_name, item.passage) for item in self._corpus
            if item.passage.ref.source_id == message.content.task.source_id
        )
        timestamp = datetime.now(UTC)
        return RetrievalResult(passages=tuple(
            RetrievedPassage(
                passage=passage, document_name=name,
                retrieval_timestamp=timestamp, retrieved_by_agent=AgentRole.RETRIEVAL,
            )
            for name, passage in passages
        ))
