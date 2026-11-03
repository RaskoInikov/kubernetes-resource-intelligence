"""Tests for process configuration."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import ValidationError

from kri import config
from kri.config import Settings, load_settings

ENVIRONMENT = {
    "KRI_K8S_CONTEXT": "kind-test",
    "KRI_K8S_NAMESPACE": "payments",
    "KRI_WORKLOAD_IMAGE": "kri-workload:test",
    "KRI_PROMETHEUS_URL": "http://prometheus.test:9090",
    "KRI_QDRANT_URL": "http://qdrant.test:6334",
    "KRI_QDRANT_COLLECTION": "kubernetes_knowledge",
    "KRI_OLLAMA_URL": "http://ollama.test:11434",
    "KRI_OLLAMA_MODEL": "test-model",
}


@pytest.fixture(autouse=True)
def isolated_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    """Keep tests independent of a developer's shell and local .env file."""

    for name in ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    load_settings.cache_clear()
    yield
    load_settings.cache_clear()


def test_load_settings_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in ENVIRONMENT.items():
        monkeypatch.setenv(name, value)

    settings = load_settings()

    assert settings.k8s_context == "kind-test"
    assert settings.k8s_namespace == "payments"
    assert settings.workload_image == "kri-workload:test"
    assert str(settings.prometheus_url) == "http://prometheus.test:9090/"
    assert str(settings.qdrant_url) == "http://qdrant.test:6334/"
    assert settings.qdrant_collection == "kubernetes_knowledge"
    assert str(settings.ollama_url) == "http://ollama.test:11434/"
    assert settings.ollama_model == "test-model"
    assert load_settings() is settings


def test_load_settings_from_dotenv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dotenv = "\n".join(f"{name}={value}" for name, value in ENVIRONMENT.items())
    (tmp_path / ".env").write_text(f"{dotenv}\n", encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.setattr(config, "PROJECT_DOTENV", tmp_path / ".env")

    settings = load_settings()

    assert settings.k8s_context == "kind-test"
    assert settings.qdrant_collection == "kubernetes_knowledge"


def test_missing_settings_are_rejected() -> None:
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)

    missing_fields = {item["loc"][0] for item in error.value.errors()}
    assert missing_fields == {
        "k8s_context",
        "k8s_namespace",
        "workload_image",
        "prometheus_url",
        "qdrant_url",
        "qdrant_collection",
        "ollama_url",
        "ollama_model",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("KRI_K8S_NAMESPACE", "   "),
        ("KRI_PROMETHEUS_URL", "prometheus.test:9090"),
    ],
)
def test_invalid_settings_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: str,
) -> None:
    for name, valid_value in ENVIRONMENT.items():
        monkeypatch.setenv(name, valid_value)
    monkeypatch.setenv(field, value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
