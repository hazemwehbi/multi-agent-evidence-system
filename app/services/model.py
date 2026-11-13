import asyncio
from collections.abc import Mapping
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from app.config import ModelMetadata, Settings
from app.models.contracts import Contract, NonEmpty

Output = TypeVar("Output", bound=BaseModel)


class ModelRequest(Contract):
    operation: NonEmpty
    instruction: NonEmpty
    input_text: NonEmpty


class ModelError(Exception):
    """Safe error text for display and tracing."""


class ModelTimeout(ModelError):
    pass


class InvalidModelOutput(ModelError):
    pass


class ModelUnavailable(ModelError):
    pass


class ModelBackend(Protocol):
    async def generate(self, request: ModelRequest, schema: type[BaseModel]) -> object: ...


class ModelClient:
    def __init__(self, metadata: ModelMetadata, backend: ModelBackend) -> None:
        self.metadata = metadata
        self._backend = backend

    async def generate(self, request: ModelRequest, schema: type[Output]) -> Output:
        try:
            async with asyncio.timeout(self.metadata.timeout_seconds):
                output = await self._backend.generate(request, schema)
        except TimeoutError:
            raise ModelTimeout("Model request timed out") from None
        except ModelError:
            raise
        except Exception:
            raise ModelUnavailable("Model request failed") from None

        try:
            return schema.model_validate(output)
        except ValidationError:
            raise InvalidModelOutput("Model output failed schema validation") from None


class OfflineBackend:
    def __init__(self, fixtures: Mapping[str, Mapping[str, object]]) -> None:
        self._fixtures = dict(fixtures)

    async def generate(self, request: ModelRequest, schema: type[BaseModel]) -> object:
        if request.operation not in self._fixtures:
            raise ModelUnavailable(f"No offline fixture for operation {request.operation!r}")
        return dict(self._fixtures[request.operation])


def build_model_client(
    settings: Settings, fixtures: Mapping[str, Mapping[str, object]]
) -> ModelClient:
    metadata = settings.model_metadata()
    if settings.provider == "offline":
        return ModelClient(metadata, OfflineBackend(fixtures))

    try:
        from app.services.openai_backend import OpenAIBackend
    except ImportError:
        raise ModelUnavailable("Install the openai project extra to enable OpenAI") from None
    return ModelClient(metadata, OpenAIBackend(settings))
