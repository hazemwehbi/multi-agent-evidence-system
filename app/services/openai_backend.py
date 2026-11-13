from langchain_openai import ChatOpenAI
from openai import APITimeoutError
from pydantic import BaseModel

from app.config import Settings
from app.services.model import InvalidModelOutput, ModelRequest, ModelTimeout, ModelUnavailable


class OpenAIBackend:
    def __init__(self, settings: Settings) -> None:
        metadata = settings.model_metadata()
        try:
            self._chat = ChatOpenAI(
                model=metadata.model,
                api_key=settings.openai_api_key,
                timeout=metadata.timeout_seconds,
                max_tokens=metadata.max_output_tokens,
                max_retries=0,
            )
        except Exception:
            raise ModelUnavailable("OpenAI client initialization failed") from None

    async def generate(self, request: ModelRequest, schema: type[BaseModel]) -> object:
        # Use the JSON schema so the common client owns local validation in both modes.
        structured = self._chat.with_structured_output(
            schema.model_json_schema(), method="json_schema", include_raw=True
        )
        try:
            response = await structured.ainvoke([
                ("system", request.instruction),
                ("human", request.input_text),
            ])
        except APITimeoutError:
            raise ModelTimeout("Model request timed out") from None
        if response["parsing_error"] is not None or response["parsed"] is None:
            raise InvalidModelOutput("OpenAI returned no usable structured output")
        return response["parsed"]
