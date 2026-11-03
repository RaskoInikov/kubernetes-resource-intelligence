"""Offline tests for local-development service diagnostics."""

from email.message import Message
from urllib.error import HTTPError, URLError

import pytest

from kri.config import Settings
from kri.dev import (
    LocalServiceError,
    check_local_services,
    main,
    probe_url,
)


def settings() -> Settings:
    return Settings(
        k8s_context="kind-test",
        k8s_namespace="payments",
        workload_image="kri-workload:local",
        prometheus_url="http://127.0.0.1:9090",
        qdrant_url="http://127.0.0.1:6333",
        qdrant_collection="kri local/knowledge",
        ollama_url="http://127.0.0.1:11434",
        ollama_model="unused",
    )


def test_required_services_are_scoped_and_all_checked() -> None:
    visited: list[str] = []

    ready = check_local_services(settings(), visited.append)

    assert ready == ("Prometheus", "Qdrant", "Qdrant collection 'kri local/knowledge'")
    assert visited == [
        "http://127.0.0.1:9090/-/ready",
        "http://127.0.0.1:6333/readyz",
        "http://127.0.0.1:6333/collections/kri%20local%2Fknowledge",
    ]


def test_preflight_reports_each_unavailable_service() -> None:
    def unavailable(url: str) -> None:
        if url.endswith("/-/ready") or "/collections/" in url:
            raise LocalServiceError("connection refused")

    with pytest.raises(LocalServiceError) as error:
        check_local_services(settings(), unavailable)

    message = str(error.value)
    assert "Prometheus unavailable" in message
    assert "start the documented kubectl port-forward" in message
    assert "Qdrant collection 'kri local/knowledge' unavailable" in message
    assert "make sync-knowledge" in message
    assert "Qdrant unavailable" not in message


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (HTTPError("http://test", 503, "no", Message(), None), "HTTP 503"),
        (URLError("connection refused"), "connection refused"),
    ],
)
def test_probe_wraps_http_failures(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    message: str,
) -> None:
    def fail(*_: object, **__: object) -> None:
        raise failure

    monkeypatch.setattr("kri.dev.urlopen", fail)
    with pytest.raises(LocalServiceError, match=message):
        probe_url("http://test/ready")


def test_probe_reads_successful_response(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self, size: int) -> bytes:
            assert size == 1
            return b"o"

    monkeypatch.setattr("kri.dev.urlopen", lambda *_args, **_kwargs: Response())
    probe_url("http://test/ready")


def test_main_reports_ready_services(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("kri.dev.load_settings", settings)
    monkeypatch.setattr(
        "kri.dev.check_local_services", lambda _: ("Prometheus", "Qdrant")
    )

    main()

    assert capsys.readouterr().out == "Local services ready: Prometheus, Qdrant\n"


def test_main_reports_configuration_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def invalid_settings() -> Settings:
        return Settings(_env_file=None)

    monkeypatch.setattr("kri.dev.load_settings", invalid_settings)
    with pytest.raises(SystemExit) as error:
        main()

    assert error.value.code == 2
    assert "Configuration error" in capsys.readouterr().err


def test_main_reports_service_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("kri.dev.load_settings", settings)

    def unavailable(_: Settings) -> tuple[str, ...]:
        raise LocalServiceError("Prometheus unavailable")

    monkeypatch.setattr("kri.dev.check_local_services", unavailable)
    with pytest.raises(SystemExit) as error:
        main()

    assert error.value.code == 1
    assert "Local service preflight failed" in capsys.readouterr().err
