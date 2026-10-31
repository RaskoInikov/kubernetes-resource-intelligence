"""Offline tests for the disposable application's image runtime."""

from http import HTTPStatus
from io import BytesIO
from typing import Any

import pytest

from deploy.workload import app, load
from deploy.workload.metrics import HttpMetrics


def _handle(
    path: str, monkeypatch: pytest.MonkeyPatch
) -> tuple[HTTPStatus, dict[str, object]]:
    handler = object.__new__(app.Handler)
    handler.path = path
    responses: list[tuple[HTTPStatus, dict[str, object]]] = []
    monkeypatch.setattr(
        handler, "_respond", lambda status, payload: responses.append((status, payload))
    )
    handler.do_GET()
    return responses[0]


def test_application_health_work_and_failure_responses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _handle("/healthz", monkeypatch)[0] is HTTPStatus.OK
    assert _handle("/work?cpu_ms=0&memory_mb=1", monkeypatch)[0] is HTTPStatus.OK
    assert _handle("/missing", monkeypatch)[0] is HTTPStatus.NOT_FOUND
    assert _handle("/work?cpu_ms=invalid", monkeypatch)[0] is HTTPStatus.BAD_REQUEST

    with pytest.raises(ValueError, match="safe bounds"):
        app.perform_work(app.MAX_CPU_MS + 1, 0)


def test_metrics_exposition_tracks_requests_errors_and_histogram() -> None:
    metrics = HttpMetrics()
    metrics.observe("GET", "/work", 200, 0.02)
    metrics.observe("GET", "/work", 500, 0.2)

    output = metrics.render()

    assert (
        'kri_http_requests_total{method="GET",route="/work",status_code="200"} 1'
        in output
    )
    assert (
        'kri_http_request_errors_total{method="GET",route="/work",status_code="500"} 1'
        in output
    )
    assert (
        'kri_http_request_errors_total{method="GET",route="/work",status_code="200"}'
        not in output
    )
    assert (
        "kri_http_request_duration_seconds_bucket"
        '{le="0.025",method="GET",route="/work"} 1' in output
    )
    assert (
        "kri_http_request_duration_seconds_bucket"
        '{le="0.25",method="GET",route="/work"} 2' in output
    )
    assert (
        "kri_http_request_duration_seconds_bucket"
        '{le="+Inf",method="GET",route="/work"} 2' in output
    )
    assert (
        'kri_http_request_duration_seconds_count{method="GET",route="/work"} 2'
        in output
    )

    with pytest.raises(ValueError, match="negative"):
        metrics.observe("GET", "/work", 200, -0.1)


def test_metrics_endpoint_is_not_self_instrumented(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics = HttpMetrics()
    metrics.observe("GET", "/work", 200, 0.01)
    monkeypatch.setattr(app, "METRICS", metrics)
    handler = object.__new__(app.Handler)
    handler.path = "/metrics"
    handler.wfile = BytesIO()
    statuses: list[HTTPStatus] = []
    monkeypatch.setattr(handler, "send_response", statuses.append)
    monkeypatch.setattr(handler, "send_header", lambda *args: None)
    monkeypatch.setattr(handler, "end_headers", lambda: None)

    before = metrics.render()
    handler.do_GET()

    assert statuses == [HTTPStatus.OK]
    assert handler.wfile.getvalue().decode() == before
    assert metrics.render() == before


@pytest.mark.parametrize("mode", ["cpu", "memory", "mixed"])
def test_load_request_modes_reach_application(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    requested: list[str] = []

    class Response:
        status = 200

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def open_url(url: str, timeout: int) -> Response:
        requested.append(url)
        assert timeout == 10
        return Response()

    monkeypatch.setattr(load, "urlopen", open_url)
    load.send_request("http://target.test/work", mode)
    assert requested[0].startswith("http://target.test/work?cpu_ms=")


def test_load_request_rejects_http_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status = 503

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(load, "urlopen", lambda *args, **kwargs: Response())
    with pytest.raises(RuntimeError, match="HTTP 503"):
        load.send_request("http://target.test/work", "cpu")


def test_load_runner_reports_success_and_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = {
        "TARGET_URL": "http://target.test/work",
        "WORKLOAD_MODE": "cpu",
        "CONCURRENCY": "1",
        "REQUEST_RATE": "1000",
        "DURATION_SECONDS": "0.001",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(load, "send_request", lambda target, mode: None)
    assert load.run() == 0

    def fail(*args: Any) -> None:
        raise RuntimeError("target failed")

    monkeypatch.setattr(load, "send_request", fail)
    assert load.run() == 1

    monkeypatch.setenv("WORKLOAD_MODE", "unknown")
    with pytest.raises(ValueError, match="WORKLOAD_MODE"):
        load.run()

    monkeypatch.setenv("WORKLOAD_MODE", "cpu")
    monkeypatch.setenv("CONCURRENCY", "0")
    with pytest.raises(ValueError, match="CONCURRENCY"):
        load.run()
