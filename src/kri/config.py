"""Validated process configuration for external service boundaries."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import AnyHttpUrl, StringConstraints
from pydantic_settings import BaseSettings, SettingsConfigDict

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
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


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    """Load cached configuration from the project root regardless of cwd."""

    return Settings(_env_file=PROJECT_DOTENV)
