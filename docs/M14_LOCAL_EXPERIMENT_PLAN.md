# M14 local controlled experiment preflight

Status: **approved on 2026-11-08; execution stopped on failed A1**. The original
preflight used read-only Kubernetes and Prometheus checks on 2026-11-06. The
execution record and inconclusive result are in
`docs/M14_LOCAL_EXPERIMENT_REPORT.md`.
This v1 plan remains immutable historical evidence; the unapproved replacement
is `docs/M14_LOCAL_EXPERIMENT_PLAN_V2.md`.
The digest-bound machine-readable plan is
`evaluation/m14-local-cpu-limit-plan-v1.json`, SHA-256
`612af134d27a524e300c6f80e36c4367b5060a3ed10d7ab34f6a90d75130062e`.

## Read-only preflight result

| Check | Observed result |
| --- | --- |
| Context / cluster | `kind-kube-optimizer` / `kind-kube-optimizer` |
| Namespace / workload | `payments` / Deployment `kri-workload` |
| Deployment identity | UID `3360fb27-d522-4b1d-9774-aa9e359e301a`, resourceVersion `1195095`, generation `1` |
| Baseline | 2 replicas; CPU `90m/140m`; memory `109Mi/192Mi` |
| Declared / runtime image | `kri-workload:local` / `docker.io/library/import-2026-10-31@sha256:ad6d70e96f19ec8472b41f2e135139da33c36fb1f22a83d23ce019f682807d91` |
| Application Pods | 2/2 Running and Ready, identical image digest; each has 3 historical restarts, last terminated at `2026-11-04T11:08:51Z` |
| Node | `kube-optimizer-control-plane` Ready; memory, disk, and PID pressure all false; allocatable 18 CPU and 32,488,352 KiB memory |
| Workload events | No retained Deployment events returned |
| Job-name collisions | None for the four proposed `kri-load-m14-*` Jobs |
| Prometheus | In-cluster Deployment and four scrape targets are healthy; **local access blocked** because no process forwards Service `kri-prometheus` to `localhost:9090` |

The live Deployment UID and exact baseline match retained real observation
`obs-ui-20261102161957`. Deterministic replay is partial/degraded because the
dedicated error counter was absent, but it contains CPU-limit saturation and
high-throttling findings. Recommendation `increase-cpu-limit` changes only the
CPU limit from `140m` to `220m`; its source analysis digest is
`6cf31468819fc03074421ccf4f8f9a7e0e8976c263ba9941b71301259bcda22e`.

## Approval gate

Execution requires a new `EffectivenessApproval` with `approved: true` bound to
the exact plan ID and digest above. Approval must explicitly cover only:

1. four plan-owned load Jobs and their later deletion;
2. one controlled application rollout from CPU limit `140m` to `220m`;
3. one rollback rollout from `220m` to the exact `140m` baseline; and
4. per-Pod error-counter initialization outside every measurement window.

The monitoring objects already match the checked-in manifest and must not be
reapplied for this condition. Restore local access with the non-persistent,
loopback-only port-forward in `docs/MONITORING_RESTORATION_PLAN.md`.
Do not start a baseline trial merely because baseline resources are already
deployed: creating its load Job is still a mutation.

Immediately before execution, repeat the preflight and abort on Deployment UID,
resourceVersion/configuration, image digest, replica, readiness, node-pressure,
or co-tenant drift. Prometheus must be Ready and scrape both application Pods
and cAdvisor. Query every M14 family over a disposable no-load interval before
creating a Job; missing data remains missing and blocks the run.

The current image exposes `kri_http_request_errors_total` only after an error.
After approval, initialize that series on **each** current application Pod with
one bounded invalid `/work` request, wait for at least two 5-second scrapes, and
start the trial window afterward. Repeat after the candidate rollout. Record
this initialization; its counter increment must remain outside all four metric
windows. If every Pod does not expose the series, stop without applying the
candidate.

## Minimal controlled design

The order is A1, A2, candidate rollout, B1, B2, rollback. This minimizes the
long-lived workload changes to one candidate rollout and one rollback. It is a
sequential design rather than randomized interleaving; the report must retain
per-trial values and population standard deviations, and any observed temporal
or co-tenant drift must be declared as a confounder and force an inconclusive
result.

| Trial | Role | Experiment ID | Observation ID | Configuration |
| --- | --- | --- | --- | --- |
| A1 | baseline 1 | `m14-base-1-20261106` | `obs-m14-base-1-20261106` | `90m/140m`, `109Mi/192Mi`, 2 replicas |
| A2 | baseline 2 | `m14-base-2-20261106` | `obs-m14-base-2-20261106` | same as A1 |
| B1 | candidate 1 | `m14-cand-1-20261106` | `obs-m14-cand-1-20261106` | `90m/220m`, `109Mi/192Mi`, 2 replicas |
| B2 | candidate 2 | `m14-cand-2-20261106` | `obs-m14-cand-2-20261106` | same as B1 |

Every trial uses mixed load, concurrency 4, target 20 requests/second, duration
120 seconds, and a 120-second observation window wholly inside the reconciled
Job start/end timestamps. Wait for terminal `succeeded`, then query the exact
`job_start_timestamp` through `job_start_timestamp + 120s` at 5-second steps.
Do not overlap trials. Require a 60-second quiet interval and unchanged health,
identity, image, resources, node conditions, and co-tenants before the next run.

The only intended workload field mutation is:

```text
/spec/template/spec/containers[name=application]/resources/limits/cpu:
  140m -> 220m
```

Use the existing bounded controller after approval; do not apply generated
prose or an evaluator output:

```bash
# Candidate rollout (after A1 and A2 only)
kri-workload deploy \
  --cpu-request 90m --cpu-limit 220m \
  --memory-request 109Mi --memory-limit 192Mi --replicas 2

# Rollback (after B1 and B2, or immediately after a candidate stop condition)
kri-workload deploy \
  --cpu-request 90m --cpu-limit 140m \
  --memory-request 109Mi --memory-limit 192Mi --replicas 2
```

For each row, start only that named Job with the matching baseline or candidate
resource values recorded in its experiment artifact:

```bash
kri-workload start-load \
  --cpu-request <90m> --cpu-limit <140m-or-220m> \
  --memory-request 109Mi --memory-limit 192Mi --replicas 2 \
  --mode mixed --concurrency 4 --request-rate 20 \
  --duration-seconds 120 --experiment-id <trial-experiment-id>
```

Stop immediately on a failed Job, unready Pod, new restart, warning event, node
pressure, image/configuration drift, or unavailable required metric. Save the
terminal experiment record and immutable observation before deleting a Job.
After B2, verify rollback separately, then delete only the four plan-owned Jobs.
Never delete the application as experiment cleanup.

## Objectives and uncertainty

The fixed effectiveness objectives are:

- reduce mean throttled-period ratio by at least 20% and to at most 0.60;
- improve target attainment by at least 10% and reach at least 0.75 (15 rps of
  the 20 rps target); and
- do not reduce throughput per average CPU core.

Guardrails allow at most 5% p95-latency regression with candidate p95 no higher
than 0.75 seconds, error ratio no higher than 1%, 100% readiness, zero candidate
container restarts, and at most 15% aggregate p95-memory regression with an
absolute 384 MiB ceiling. M14 policy requires every objective and every
guardrail to pass. Missing/incomparable signals, lifecycle failures, digest
mismatches, fewer than two trials per role, or declared confounders produce
`inconclusive`, not success.

Two trials per role are the minimum M14 design. Means and population standard
deviations preserve observed variation, but four sequential local-kind trials
do not establish a production effect or a confidence interval. Historical
restart counts reset with rollout-created Pods and are not an interval restart
rate; the stop checks and observations must therefore record Pod UIDs and any
new restart/event explicitly.

## Artifacts and evaluation

Retain experiment records under `results/experiments/` and observations under
`results/observations/`. After all four trials, create a digest-bound manifest
with the four distinct role/repetition pairs and exact file SHA-256 values.
Run the offline evaluator only after rollback and cleanup status are recorded:

```bash
python scripts/evaluate_ab_experiments.py \
  --m14-plan evaluation/m14-local-cpu-limit-plan-v1.json \
  --m14-approval evaluation/<explicit-approved-record>.json \
  --m14-trials evaluation/<four-trial-manifest>.json \
  --report-id m14-kri-workload-cpu-limit-20261106 \
  --rollback-status verified --cleanup-status verified \
  --output results/effectiveness/m14-kri-workload-cpu-limit-20261106.json
```

The evaluator is read-only and cannot perform the proposed rollout, rollback,
Job cleanup, or monitoring installation.
