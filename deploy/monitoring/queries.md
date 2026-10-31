# M2 Canonical PromQL

All queries select the disposable application container in the `payments`
namespace. Empty query results mean missing data and must not be replaced by
zero.

## CPU usage (cores per pod)

```promql
sum by (namespace, pod, container) (
  rate(container_cpu_usage_seconds_total{
    namespace="payments", pod=~"kri-workload-.*", container="application"
  }[1m])
)
```

## CPU throttling

Throttled seconds per second:

```promql
sum by (namespace, pod, container) (
  rate(container_cpu_cfs_throttled_seconds_total{
    namespace="payments", pod=~"kri-workload-.*", container="application"
  }[1m])
)
```

Fraction of CFS periods throttled:

```promql
sum by (namespace, pod, container) (
  rate(container_cpu_cfs_throttled_periods_total{
    namespace="payments", pod=~"kri-workload-.*", container="application"
  }[1m])
)
/
sum by (namespace, pod, container) (
  rate(container_cpu_cfs_periods_total{
    namespace="payments", pod=~"kri-workload-.*", container="application"
  }[1m])
)
```

## Memory working set (bytes per pod)

```promql
sum by (namespace, pod, container) (
  container_memory_working_set_bytes{
    namespace="payments", pod=~"kri-workload-.*", container="application"
  }
)
```

## HTTP throughput (requests per second)

```promql
sum by (namespace, pod) (
  rate(kri_http_requests_total{namespace="payments", route="/work"}[1m])
)
```

## HTTP errors (errors per second)

```promql
sum by (namespace, pod, status_code) (
  rate(kri_http_request_errors_total{namespace="payments", route="/work"}[1m])
)
```

## HTTP latency p95 (seconds)

```promql
histogram_quantile(
  0.95,
  sum by (namespace, pod, le) (
    rate(kri_http_request_duration_seconds_bucket{
      namespace="payments", route="/work"
    }[1m])
  )
)
```
