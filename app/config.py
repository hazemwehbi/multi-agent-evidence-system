from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, SecretStr, StringConstraints, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ModelName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Timeout = Annotated[float, Field(gt=0, le=120)]
TokenLimit = Annotated[int, Field(ge=128, le=8192)]


class ModelMetadata(BaseModel, frozen=True, extra="forbid"):
    provider: Literal["offline", "openai"]
    model: ModelName
    timeout_seconds: Timeout
    max_output_tokens: TokenLimit


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MAEDS_", env_file=".env", env_file_encoding="utf-8",
        extra="ignore", hide_input_in_errors=True,
    )

    provider: Literal["offline", "openai"] = "offline"
    model: ModelName | None = None
    model_timeout_seconds: Timeout = 15
    max_output_tokens: TokenLimit = 512
    openai_api_key: SecretStr | None = Field(
        default=None, validation_alias="OPENAI_API_KEY", exclude=True
    )

    @model_validator(mode="after")
    def validate_provider(self) -> Self:
        if self.provider == "openai":
            if self.model is None:
                raise ValueError("OpenAI mode requires MAEDS_MODEL")
            if self.openai_api_key is None or not self.openai_api_key.get_secret_value().strip():
                raise ValueError("OpenAI mode requires OPENAI_API_KEY")
        elif self.model not in (None, "deterministic-v1"):
            raise ValueError("Offline mode uses deterministic-v1")
        return self

    def model_metadata(self) -> ModelMetadata:
        return ModelMetadata(
            provider=self.provider,
            model=self.model or "deterministic-v1",
            timeout_seconds=self.model_timeout_seconds,
            max_output_tokens=self.max_output_tokens,
        )
