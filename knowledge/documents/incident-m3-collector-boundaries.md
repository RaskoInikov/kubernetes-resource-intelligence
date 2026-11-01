# Incident: M3 Prometheus Boundary and Label Mismatch

## Classification

Historical project incident. Resolved and regression-tested on 2026-10-31.

## Recorded evidence

Real M3 verification queried the disposable workload in `payments` on context
`kind-kube-optimizer`. Initial collection exposed two independent defects:

1. Prometheus range boundaries were serialized with precision inconsistent with
   the service response, allowing legitimate millisecond-boundary samples to be
   rejected as outside the interval.
2. Application selection expected a nonexistent `workload` label although the
   monitored application used `job="kri-workload"`.

After correction, the post-error range collected all ten expected metric
families, 68 series, and 1,360 samples. Five controlled HTTP 400 responses were
preserved in the raw error counter. Samples ranged from `17:07:29Z` through
`17:09:04Z` inside the recorded UTC interval.

## Resolution

- Match Prometheus millisecond precision at interval boundaries.
- Scope application queries with the real stable `job` label plus namespace,
  Pod identity, and application container.
- Keep empty expected families as explicit missing data rather than zero.

## Lessons

Selector assumptions and timestamp precision are part of a collector contract.
Mocks must cover them, but only real-service verification can confirm the labels
and precision actually exposed by the monitored system.
