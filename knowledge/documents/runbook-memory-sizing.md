# Runbook: Diagnose Memory Requests and Limits

## Trigger

Use this runbook when memory working set exceeds its request, approaches its
limit, trends upward, or accompanies OOM events or container restarts.

## Required evidence

- Per-Pod/container working-set samples with timestamps.
- Configured memory request and limit for the same container.
- Pod restart counts and relevant Kubernetes events.
- Observation quality, sample count, interval, and missing-data findings.

## Procedure

1. Verify workload identity and container scope.
2. Calculate mean, p95, and maximum working set for the recorded interval.
3. Compare p95 with the request to assess scheduling representation.
4. Compare maximum with the limit and inspect OOM or restart evidence to assess
   runtime safety.
5. Treat findings close to a threshold as sensitive to normal variation,
   especially when only one replica crosses the boundary.
6. Do not infer a leak from a high percentile alone; inspect longer windows and
   trend behavior.
7. Bound any increase, preserve request at or below limit, and require approval.

## Interpretation

A low memory request can understate scheduling demand without indicating memory
pressure. A high limit-relative maximum, OOM event, or restart is different
evidence and may justify a limit change. Keep those conclusions separate.

## Verification and rollback

Repeat a comparable bounded experiment after an approved change. Verify working
set, OOM events, restarts, scheduling behavior, and node pressure. Retain the old
and new observations so the change remains auditable.
