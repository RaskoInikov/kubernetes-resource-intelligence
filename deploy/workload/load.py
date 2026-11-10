"""Rate-controlled load generator for the disposable application."""

import json
import os
import time
from collections import Counter
from queue import Empty, SimpleQueue
from threading import Thread
from urllib.error import URLError
from urllib.request import urlopen

WORK = {
    "cpu": (25, 0),
    "memory": (0, 32),
    "mixed": (25, 32),
}
SHUTDOWN_GRACE_SECONDS = 1.0
SHUTDOWN_POLL_SECONDS = 0.01
EXIT_STUCK_WORKER = 4

_SUCCEEDED = "succeeded"
_FAILED = "request_failure"
_TIMED_OUT = "request_timeout"


def _positive(name: str, cast: type[int] | type[float]) -> int | float:
    value = cast(os.environ[name])
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def send_request(target: str, mode: str, timeout_seconds: float = 10.0) -> None:
    cpu_ms, memory_mb = WORK[mode]
    with urlopen(
        f"{target}?cpu_ms={cpu_ms}&memory_mb={memory_mb}",
        timeout=timeout_seconds,
    ) as response:
        if response.status != 200:
            raise RuntimeError(f"target returned HTTP {response.status}")


def _send_and_record(
    target: str,
    mode: str,
    timeout_seconds: float,
    outcomes: SimpleQueue[str],
) -> None:
    """Run one request and retain its distinct terminal outcome."""

    try:
        send_request(target, mode, timeout_seconds)
    except Exception as error:
        if isinstance(error, TimeoutError) or (
            isinstance(error, URLError) and isinstance(error.reason, TimeoutError)
        ):
            outcomes.put(_TIMED_OUT)
        else:
            outcomes.put(_FAILED)
    else:
        outcomes.put(_SUCCEEDED)


def _collect_completed(
    workers: set[Thread], outcomes: SimpleQueue[str]
) -> Counter[str]:
    """Discard completed workers and return every newly recorded outcome."""

    completed = {worker for worker in workers if not worker.is_alive()}
    for worker in completed:
        worker.join()
    workers.difference_update(completed)
    collected: Counter[str] = Counter()
    while True:
        try:
            collected[outcomes.get_nowait()] += 1
        except Empty:
            return collected


def _finish(counts: Counter[str], started: int, stuck_workers: int) -> int:
    """Emit client outcomes and fail only for generator execution failure."""

    exit_code = EXIT_STUCK_WORKER if stuck_workers else 0
    summary = {
        "schema_version": "1.1",
        "execution_status": "failed" if stuck_workers else "completed",
        "execution_failure_reason": "stuck_worker" if stuck_workers else None,
        "exit_code": exit_code,
        "requests_started": started,
        "requests_completed": sum(counts.values()),
        "requests_succeeded": counts[_SUCCEEDED],
        "request_failures": counts[_FAILED],
        "request_timeouts": counts[_TIMED_OUT],
        "stuck_workers": stuck_workers,
    }
    encoded = json.dumps(summary, sort_keys=True)
    print(encoded, flush=True)
    termination_log = os.environ.get("TERMINATION_LOG_PATH")
    if termination_log is not None:
        with open(termination_log, "w", encoding="utf-8") as destination:
            destination.write(f"{encoded}\n")
    return exit_code


def run() -> int:
    """Generate load and return nonzero only for execution failure."""

    target = os.environ["TARGET_URL"]
    mode = os.environ["WORKLOAD_MODE"]
    if mode not in WORK:
        raise ValueError("WORKLOAD_MODE must be cpu, memory, or mixed")
    concurrency = int(_positive("CONCURRENCY", int))
    request_rate = float(_positive("REQUEST_RATE", float))
    duration = float(_positive("DURATION_SECONDS", float))
    interval = 1 / request_rate
    deadline = time.monotonic() + duration
    next_request = time.monotonic()
    workers: set[Thread] = set()
    outcomes: SimpleQueue[str] = SimpleQueue()
    counts: Counter[str] = Counter()
    started = 0
    while True:
        now = time.monotonic()
        counts.update(_collect_completed(workers, outcomes))
        if now >= deadline:
            break
        until_next_request = next_request - now
        if until_next_request > 0:
            time.sleep(min(until_next_request, deadline - now))
            continue
        if len(workers) < concurrency:
            timeout_seconds = min(10.0, deadline - now)
            worker = Thread(
                target=_send_and_record,
                args=(target, mode, timeout_seconds, outcomes),
                daemon=True,
                name="kri-load-request",
            )
            workers.add(worker)
            worker.start()
            started += 1
        next_request = now + interval

    shutdown_deadline = time.monotonic() + SHUTDOWN_GRACE_SECONDS
    while workers:
        counts.update(_collect_completed(workers, outcomes))
        remaining = shutdown_deadline - time.monotonic()
        if not workers or remaining <= 0:
            break
        time.sleep(min(SHUTDOWN_POLL_SECONDS, remaining))
    counts.update(_collect_completed(workers, outcomes))
    return _finish(counts, started, len(workers))


if __name__ == "__main__":
    raise SystemExit(run())
