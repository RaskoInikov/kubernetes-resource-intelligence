"""Minimal thread-safe Prometheus metrics for the disposable HTTP target."""

from collections import defaultdict
from threading import Lock

HISTOGRAM_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)


def _labels(**labels: str) -> str:
    def escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    values = ",".join(
        f'{name}="{escape(value)}"' for name, value in sorted(labels.items())
    )
    return f"{{{values}}}"


class HttpMetrics:
    """Record bounded-label HTTP counters and duration histograms."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._requests: defaultdict[tuple[str, str, str], int] = defaultdict(int)
        self._errors: defaultdict[tuple[str, str, str], int] = defaultdict(int)
        self._counts: defaultdict[tuple[str, str], int] = defaultdict(int)
        self._sums: defaultdict[tuple[str, str], float] = defaultdict(float)
        self._buckets: defaultdict[tuple[str, str, float], int] = defaultdict(int)

    def observe(
        self,
        method: str,
        route: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        """Record one completed request."""

        if duration_seconds < 0:
            raise ValueError("request duration cannot be negative")
        status = str(status_code)
        with self._lock:
            self._requests[(method, route, status)] += 1
            if status_code >= 400:
                self._errors[(method, route, status)] += 1
            self._counts[(method, route)] += 1
            self._sums[(method, route)] += duration_seconds
            for bucket in HISTOGRAM_BUCKETS:
                if duration_seconds <= bucket:
                    self._buckets[(method, route, bucket)] += 1

    def render(self) -> str:
        """Render a consistent Prometheus text exposition snapshot."""

        with self._lock:
            requests = dict(self._requests)
            errors = dict(self._errors)
            counts = dict(self._counts)
            sums = dict(self._sums)
            buckets = dict(self._buckets)

        lines = [
            "# HELP kri_http_requests_total Completed HTTP requests.",
            "# TYPE kri_http_requests_total counter",
        ]
        for (method, route, status), value in sorted(requests.items()):
            labels = _labels(method=method, route=route, status_code=status)
            lines.append(f"kri_http_requests_total{labels} {value}")
        lines.extend(
            [
                "# HELP kri_http_request_errors_total HTTP error responses.",
                "# TYPE kri_http_request_errors_total counter",
            ]
        )
        for (method, route, status), value in sorted(errors.items()):
            labels = _labels(method=method, route=route, status_code=status)
            lines.append(f"kri_http_request_errors_total{labels} {value}")
        lines.extend(
            [
                "# HELP kri_http_request_duration_seconds Request duration in seconds.",
                "# TYPE kri_http_request_duration_seconds histogram",
            ]
        )
        for method, route in sorted(counts):
            for bucket in HISTOGRAM_BUCKETS:
                labels = _labels(method=method, route=route, le=str(bucket))
                value = buckets.get((method, route, bucket), 0)
                lines.append(
                    f"kri_http_request_duration_seconds_bucket{labels} {value}"
                )
            labels = _labels(method=method, route=route, le="+Inf")
            count = counts[(method, route)]
            lines.append(f"kri_http_request_duration_seconds_bucket{labels} {count}")
            base_labels = _labels(method=method, route=route)
            total = sums[(method, route)]
            lines.append(f"kri_http_request_duration_seconds_sum{base_labels} {total}")
            lines.append(
                f"kri_http_request_duration_seconds_count{base_labels} {count}"
            )
        return "\n".join(lines) + "\n"
