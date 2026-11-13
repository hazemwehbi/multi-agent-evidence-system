import asyncio

import pytest
from pydantic import ValidationError

from app.cli import SmokeOutput
from app.config import Settings
from app.services.model import (
    InvalidModelOutput,
    ModelClient,
    ModelRequest,
    ModelTimeout,
    ModelUnavailable,
    build_model_client,
)


REQUEST = ModelRequest(operation="test", instruction="Return ready.", input_text="Check.")


def test_offline_model_is_deterministic():
    client = build_model_client(Settings(), {"test": {"status": "ready"}})
    first = asyncio.run(client.generate(REQUEST, SmokeOutput))
    second = asyncio.run(client.generate(REQUEST, SmokeOutput))
    assert first == second == SmokeOutput(status="ready")
    assert client.metadata.model == "deterministic-v1"


class FaultBackend:
    def __init__(self, fault):
        self.fault = fault
        self.cancelled = False

    async def generate(self, request, schema):
        if self.fault == "timeout":
            try:
                await asyncio.Future()
            finally:
                self.cancelled = True
        if self.fault == "failure":
            raise RuntimeError("private provider details")
        return {"status": "unexpected"}


@pytest.mark.parametrize(
    ("fault", "expected"),
    [
        ("timeout", ModelTimeout),
        ("failure", ModelUnavailable),
        ("malformed", InvalidModelOutput),
    ],
)
def test_model_boundary_classifies_faults(fault, expected):
    backend = FaultBackend(fault)
    settings = Settings(model_timeout_seconds=0.02)
    client = ModelClient(settings.model_metadata(), backend)
    with pytest.raises(expected) as caught:
        asyncio.run(client.generate(REQUEST, SmokeOutput))
    assert "private provider details" not in str(caught.value)
    assert backend.cancelled == (fault == "timeout")


def test_configuration_uses_environment_without_exporting_credentials(monkeypatch):
    monkeypatch.setenv("MAEDS_PROVIDER", "openai")
    monkeypatch.setenv("MAEDS_MODEL", "example-model")
    monkeypatch.setenv("MAEDS_MODEL_TIMEOUT_SECONDS", "9")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-secret")
    settings = Settings()
    assert settings.model_metadata().model_dump() == {
        "provider": "openai",
        "model": "example-model",
        "timeout_seconds": 9,
        "max_output_tokens": 512,
    }
    assert "dummy-secret" not in settings.model_dump_json()


def test_openai_requires_credentials(monkeypatch):
    monkeypatch.setenv("MAEDS_PROVIDER", "openai")
    monkeypatch.setenv("MAEDS_MODEL", "example-model")
    with pytest.raises(ValidationError, match="requires OPENAI_API_KEY"):
        Settings()
