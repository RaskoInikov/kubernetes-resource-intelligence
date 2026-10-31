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


def send_request(target: str, mode: str) -> None:
    cpu_ms, memory_mb = WORK[mode]
    with urlopen(
        f"{target}?cpu_ms={cpu_ms}&memory_mb={memory_mb}", timeout=10
    ) as response:
        if response.status != 200:
            raise RuntimeError(f"target returned HTTP {response.status}")


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
    futures: list[Future[None]] = []
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        while next_request < deadline:
            remaining = next_request - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)
            futures.append(executor.submit(send_request, target, mode))
            next_request += interval
    return int(any(future.exception() is not None for future in futures))


if __name__ == "__main__":
    raise SystemExit(run())
