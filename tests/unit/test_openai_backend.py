import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

pytest.importorskip("langchain_openai")

from app.cli import smoke_check
from app.config import Settings


def test_openai_adapter_uses_shared_smoke_contract(monkeypatch):
    runnable = Mock()
    runnable.ainvoke = AsyncMock(
        return_value={"parsed": {"status": "ready"}, "parsing_error": None}
    )
    chat = Mock()
    chat.with_structured_output.return_value = runnable
    factory = Mock(return_value=chat)
    monkeypatch.setattr("app.services.openai_backend.ChatOpenAI", factory)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    report = asyncio.run(smoke_check(Settings(provider="openai", model="example-model")))

    assert report.result.status == "ready"
    assert report.model.provider == "openai"
    assert factory.call_args.kwargs["max_retries"] == 0
    assert factory.call_args.kwargs["model"] == "example-model"
    assert chat.with_structured_output.call_args.kwargs["method"] == "json_schema"
    runnable.ainvoke.assert_awaited_once()
    assert "test-key" not in report.model_dump_json()
