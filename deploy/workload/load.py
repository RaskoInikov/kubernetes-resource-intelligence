"""Rate-controlled load generator for the disposable application."""

import os
import time
from concurrent.futures import Future, ThreadPoolExecutor
from urllib.request import urlopen

WORK = {
    "cpu": (25, 0),
    "memory": (0, 32),
    "mixed": (25, 32),
}


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


def _collect_completed(futures: set[Future[None]]) -> bool:
    """Discard completed work and report whether any request failed."""

    completed = {future for future in futures if future.done()}
    futures.difference_update(completed)
    return any(future.exception() is not None for future in completed)


def run() -> int:
    """Generate configured load, returning nonzero when any request fails."""

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
    futures: set[Future[None]] = set()
    failed = False
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        while True:
            now = time.monotonic()
            failed = _collect_completed(futures) or failed
            if now >= deadline:
                break
            until_next_request = next_request - now
            if until_next_request > 0:
                time.sleep(min(until_next_request, deadline - now))
                continue
            if len(futures) < concurrency:
                timeout_seconds = min(10.0, deadline - now)
                futures.add(
                    executor.submit(send_request, target, mode, timeout_seconds)
                )
            next_request = now + interval
    return int(_collect_completed(futures) or failed)


if __name__ == "__main__":
    raise SystemExit(run())
