"""Validated process configuration for external service boundaries."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import AnyHttpUrl, Field, StringConstraints
from pydantic_settings import BaseSettings, SettingsConfigDict

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Sha256Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROJECT_DOTENV = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Configuration loaded from ``KRI_`` environment variables."""

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        env_prefix="KRI_",
        extra="ignore",
        frozen=True,
    )

    k8s_context: NonEmptyString
    k8s_namespace: NonEmptyString
    workload_image: NonEmptyString
    prometheus_url: AnyHttpUrl
    qdrant_url: AnyHttpUrl
    qdrant_collection: NonEmptyString
    ollama_url: AnyHttpUrl
    ollama_model: NonEmptyString
    ollama_model_digest: Sha256Digest | None = None
    ollama_timeout_seconds: float = Field(default=180, gt=0, le=1800)
    llm_temperature: float = Field(default=0.0, ge=0, le=2)
    llm_seed: int = Field(default=42, ge=0, le=2_147_483_647)
    llm_context_tokens: int = Field(default=8192, ge=1024, le=131_072)
    llm_max_output_tokens: int = Field(default=2048, ge=128, le=16_384)


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    """Load cached configuration from the project root regardless of cwd."""

    return Settings(_env_file=PROJECT_DOTENV)
