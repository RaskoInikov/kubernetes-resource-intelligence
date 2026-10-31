"""Small disposable HTTP target with bounded CPU and memory work."""

import json
import time
from collections.abc import Mapping
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .metrics import HttpMetrics

MAX_CPU_MS = 1000
MAX_MEMORY_MB = 512
METRICS = HttpMetrics()


def perform_work(cpu_ms: int, memory_mb: int) -> dict[str, int]:
    """Perform bounded synthetic work and report requested amounts."""

    if not 0 <= cpu_ms <= MAX_CPU_MS or not 0 <= memory_mb <= MAX_MEMORY_MB:
        raise ValueError("work request is outside safe bounds")
    allocation = bytearray(memory_mb * 1024 * 1024)
    for offset in range(0, len(allocation), 4096):
        allocation[offset] = 1
    deadline = time.perf_counter() + cpu_ms / 1000
    iterations = 0
    while time.perf_counter() < deadline:
        iterations += 1
    return {"cpu_ms": cpu_ms, "memory_mb": memory_mb, "iterations": iterations}


class Handler(BaseHTTPRequestHandler):
    """Serve health and bounded work endpoints."""

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/metrics":
            self._respond_metrics()
            return
        started = time.perf_counter()
        route = parsed.path if parsed.path in {"/healthz", "/work"} else "unknown"
        if parsed.path == "/healthz":
            self._complete(started, route, HTTPStatus.OK, {"status": "ok"})
            return
        if parsed.path != "/work":
            self._complete(started, route, HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        try:
            query = parse_qs(parsed.query)
            result = perform_work(
                int(query.get("cpu_ms", ["0"])[0]),
                int(query.get("memory_mb", ["0"])[0]),
            )
        except (ValueError, TypeError) as error:
            self._complete(
                started, route, HTTPStatus.BAD_REQUEST, {"error": str(error)}
            )
            return
        self._complete(started, route, HTTPStatus.OK, result)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _respond(self, status: HTTPStatus, payload: Mapping[str, object]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _complete(
        self,
        started: float,
        route: str,
        status: HTTPStatus,
        payload: Mapping[str, object],
    ) -> None:
        self._respond(status, payload)
        METRICS.observe("GET", route, status, time.perf_counter() - started)

    def _respond_metrics(self) -> None:
        body = METRICS.render().encode()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
