"""Read-only diagnostics for the local M11 development workflow."""

import json
import sys
from collections.abc import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from pydantic import ValidationError

from kri.config import PROJECT_DOTENV, Settings, load_settings


class LocalServiceError(RuntimeError):
    """One actionable local-development readiness failure."""


def probe_url(url: str) -> None:
    """Require one HTTP endpoint to return a successful response."""

    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=3) as response:
            response.read(1)
    except HTTPError as error:
        raise LocalServiceError(f"HTTP {error.code}") from error
    except URLError as error:
        raise LocalServiceError(str(error.reason)) from error


def required_endpoints(settings: Settings) -> tuple[tuple[str, str, str], ...]:
    """Return named readiness probes and their recovery instructions."""

    prometheus = str(settings.prometheus_url).rstrip("/")
    qdrant = str(settings.qdrant_url).rstrip("/")
    collection = quote(settings.qdrant_collection, safe="")
    return (
        (
            "Prometheus",
            f"{prometheus}/-/ready",
            "start the documented kubectl port-forward",
        ),
        (
            "Qdrant",
            f"{qdrant}/readyz",
            "start the documented local Qdrant container",
        ),
        (
            f"Qdrant collection {settings.qdrant_collection!r}",
            f"{qdrant}/collections/{collection}",
            "run `make sync-knowledge` after Qdrant is ready",
        ),
    )


def check_local_services(
    settings: Settings,
    probe: Callable[[str], None] = probe_url,
) -> tuple[str, ...]:
    """Probe every dependency and report all failures together."""

    ready: list[str] = []
    failures: list[str] = []
    for name, url, recovery in required_endpoints(settings):
        try:
            probe(url)
        except LocalServiceError as error:
            failures.append(f"{name} unavailable at {url}: {error}; {recovery}")
        else:
            ready.append(name)
    if failures:
        raise LocalServiceError("\n".join(failures))
    return tuple(ready)


def main() -> None:
    """Validate root configuration and print a concise readiness result."""

    try:
        settings = load_settings()
    except ValidationError as error:
        print(
            f"Configuration error: expected required KRI_ values in {PROJECT_DOTENV}",
            file=sys.stderr,
        )
        print(json.dumps(error.errors(), indent=2, default=str), file=sys.stderr)
        raise SystemExit(2) from error
    try:
        ready = check_local_services(settings)
    except LocalServiceError as error:
        print(f"Local service preflight failed:\n{error}", file=sys.stderr)
        raise SystemExit(1) from error
    print(f"Local services ready: {', '.join(ready)}")
