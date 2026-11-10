"""Offline tests for the disposable application's image runtime."""

import json
from http import HTTPStatus
from io import BytesIO
from pathlib import Path
from threading import Event
from time import monotonic, sleep
from typing import Any, cast
from urllib.error import URLError

import pytest

from deploy.workload import app, load
from deploy.workload.metrics import HttpMetrics


def _load_summary(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads(capsys.readouterr().out.strip().splitlines()[-1]),
    )


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
    capsys: pytest.CaptureFixture[str],
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
    monkeypatch.setattr(
        load, "send_request", lambda target, mode, timeout_seconds: None
    )
    assert load.run() == 0
    success = _load_summary(capsys)
    assert success["schema_version"] == "1.1"
    assert success["execution_status"] == "completed"
    assert success["execution_failure_reason"] is None
    assert success["exit_code"] == 0
    assert success["requests_started"] == success["requests_succeeded"]
    assert success["requests_completed"] == success["requests_started"]
    assert success["request_failures"] == 0
    assert success["request_timeouts"] == 0
    assert success["stuck_workers"] == 0

    def fail(*args: Any) -> None:
        raise RuntimeError("target failed")

    monkeypatch.setattr(load, "send_request", fail)
    assert load.run() == 0
    failure = _load_summary(capsys)
    assert failure["execution_status"] == "completed"
    assert failure["execution_failure_reason"] is None
    assert failure["exit_code"] == 0
    assert failure["request_failures"] == failure["requests_started"]
    assert failure["request_timeouts"] == 0
    assert failure["stuck_workers"] == 0

    monkeypatch.setenv("WORKLOAD_MODE", "unknown")
    with pytest.raises(ValueError, match="WORKLOAD_MODE"):
        load.run()

    monkeypatch.setenv("WORKLOAD_MODE", "cpu")
    monkeypatch.setenv("CONCURRENCY", "0")
    with pytest.raises(ValueError, match="CONCURRENCY"):
        load.run()


@pytest.mark.parametrize(
    ("error", "outcome"),
    [
        (TimeoutError("direct timeout"), "request_timeout"),
        (URLError(TimeoutError("wrapped timeout")), "request_timeout"),
        (URLError("dns failure"), "request_failure"),
    ],
)
def test_load_runner_distinguishes_timeouts_from_other_failures(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
    outcome: str,
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

    def fail(*args: Any) -> None:
        raise error

    monkeypatch.setattr(load, "send_request", fail)

    assert load.run() == 0
    summary = _load_summary(capsys)
    assert summary["execution_status"] == "completed"
    assert summary["execution_failure_reason"] is None
    assert summary["exit_code"] == 0
    expected_timeouts = (
        summary["requests_started"] if outcome == "request_timeout" else 0
    )
    expected_failures = (
        summary["requests_started"] if outcome == "request_failure" else 0
    )
    assert summary["request_timeouts"] == expected_timeouts
    assert summary["request_failures"] == expected_failures


def test_load_runner_bounds_in_flight_work_and_shutdown_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = {
        "TARGET_URL": "http://target.test/work",
        "WORKLOAD_MODE": "mixed",
        "CONCURRENCY": "2",
        "REQUEST_RATE": "10000",
        "DURATION_SECONDS": "0.05",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    timeouts: list[float] = []

    def throttled_request(target: str, mode: str, timeout_seconds: float) -> None:
        assert target == "http://target.test/work"
        assert mode == "mixed"
        timeouts.append(timeout_seconds)
        sleep(timeout_seconds)

    monkeypatch.setattr(load, "send_request", throttled_request)

    started = monotonic()
    result = load.run()
    elapsed = monotonic() - started

    assert result == 0
    assert 1 <= len(timeouts) <= 2
    assert all(0 < timeout <= 0.05 for timeout in timeouts)
    assert elapsed < 0.15


def test_load_runner_does_not_wait_forever_for_a_stuck_request(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = {
        "TARGET_URL": "http://target.test/work",
        "WORKLOAD_MODE": "mixed",
        "CONCURRENCY": "1",
        "REQUEST_RATE": "10000",
        "DURATION_SECONDS": "0.02",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(load, "SHUTDOWN_GRACE_SECONDS", 0.02)
    release = Event()
    started = Event()

    def stuck_request(target: str, mode: str, timeout_seconds: float) -> None:
        started.set()
        release.wait(timeout=1)

    monkeypatch.setattr(load, "send_request", stuck_request)

    before = monotonic()
    try:
        result = load.run()
    finally:
        release.set()
    elapsed = monotonic() - before

    assert started.is_set()
    assert result == load.EXIT_STUCK_WORKER
    assert elapsed < 0.15
    summary = _load_summary(capsys)
    assert summary["execution_status"] == "failed"
    assert summary["execution_failure_reason"] == "stuck_worker"
    assert summary["exit_code"] == load.EXIT_STUCK_WORKER
    assert summary["requests_started"] == 1
    assert summary["requests_completed"] == 0
    assert summary["stuck_workers"] == 1


def test_load_runner_preserves_client_outcomes_during_execution_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = {
        "TARGET_URL": "http://target.test/work",
        "WORKLOAD_MODE": "mixed",
        "CONCURRENCY": "3",
        "REQUEST_RATE": "10000",
        "DURATION_SECONDS": "0.02",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(load, "SHUTDOWN_GRACE_SECONDS", 0.02)
    release = Event()
    calls = 0

    def mixed_failure(target: str, mode: str, timeout_seconds: float) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("request failed")
        if calls == 2:
            raise TimeoutError("request timed out")
        release.wait(timeout=1)

    monkeypatch.setattr(load, "send_request", mixed_failure)

    try:
        result = load.run()
    finally:
        release.set()

    assert result == load.EXIT_STUCK_WORKER
    summary = _load_summary(capsys)
    assert summary["execution_status"] == "failed"
    assert summary["execution_failure_reason"] == "stuck_worker"
    assert summary["exit_code"] == load.EXIT_STUCK_WORKER
    assert summary["request_failures"] == 1
    assert summary["request_timeouts"] == 1
    assert summary["stuck_workers"] == 3
    assert summary["requests_started"] == cast(int, summary["requests_completed"]) + 3


def test_load_runner_writes_identical_explicit_termination_log(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    termination_log = tmp_path / "termination.log"
    for name, value in {
        "TARGET_URL": "http://target.test/work",
        "WORKLOAD_MODE": "cpu",
        "CONCURRENCY": "1",
        "REQUEST_RATE": "1000",
        "DURATION_SECONDS": "0.001",
        "TERMINATION_LOG_PATH": str(termination_log),
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(
        load, "send_request", lambda target, mode, timeout_seconds: None
    )

    assert load.run() == 0

    stdout = capsys.readouterr().out.strip()
    assert termination_log.read_text(encoding="utf-8").strip() == stdout
