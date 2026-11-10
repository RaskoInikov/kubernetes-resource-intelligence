# M14 local controlled experiment report v3

## Outcome

Execution was explicitly approved on 2026-11-09 for plan
`m14-kri-workload-cpu-limit-20261109-v3`, digest
`0a384b519d69d0242ba739b797e0235f0d943f77f9cc74bb416985d476c4a3d4`.
The full read-only preflight passed. A1 used the corrected cached image and ran
for the complete 120-second load interval, but its container exited 1 and the
Job reached `Failed`/`BackoffLimitExceeded`. The mandatory failed-Job stop rule
prevented A2, the candidate rollout, B1, and B2 from starting.

The M14 classification is **`inconclusive`**. A1 measurements are retained but
cannot become a valid baseline because its lifecycle was not `succeeded`. No
candidate configuration was deployed, so none of the three objectives or five
guardrails can be decided. This is not evidence for or against the `220m` CPU
limit recommendation.

## Preflight and image resolution

Immediately before mutation:

- approval matched the exact v3 plan ID and digest;
- Deployment `payments/kri-workload` retained UID/resourceVersion
  `3360fb27-d522-4b1d-9774-aa9e359e301a`/`1195095`, generation 1, target image
  digest
  `import-2026-10-31@sha256:ad6d70e96f19ec8472b41f2e135139da33c36fb1f22a83d23ce019f682807d91`,
  CPU `90m/140m`, memory `109Mi/192Mi`, and 2/2 readiness;
- cached load tag `kri-workload:lifecycle-smoke-20261109` and runtime digest
  `import-2026-11-09@sha256:c0cd3e143d5bb04237340cdea0bc14b0709cce17911152a34faa375bc7e5889e`
  were present on the kind node;
- all v3 Job and artifact IDs were absent;
- node pressure was false, Prometheus was Ready, and co-tenants were stable;
- all ten metric families returned 70 series and 350 samples over the no-load
  preflight window without missing data; and
- the only retained warning events were v2 image-pull failures before the v3
  approval time.

The two approved baseline error-counter initialization requests returned the
expected HTTP 400 outside the measurement window. Application readiness and
restart counts stayed unchanged after two scrapes.

A1's single Pod used `imagePullPolicy: Never`, immediately resolved the cached
tag to the required runtime digest, and had zero restarts. No image pull or
image-resolution warning occurred. Job controls matched `backoffLimit: 0` and
`activeDeadlineSeconds: 180`.

## A1 lifecycle and measurements

| Field | Recorded value |
| --- | --- |
| Experiment | `m14v3-base-1-20261109` |
| Job UID | `444028b6-47d3-4c1d-9ee6-6ad3d41a4dde` |
| Pod UID | `bf43c34b-81e6-4388-8b5c-b90b52cb0edf` |
| Kubernetes start | `2026-11-09T08:11:28Z` |
| Container finish | `2026-11-09T08:13:30Z` |
| Kubernetes terminal time | `2026-11-09T08:13:32Z` |
| Container exit | `1` / `Error` |
| Job terminal state | `failed` / `BackoffLimitExceeded` |
| Observation window | `2026-11-09T08:11:28Z` through `2026-11-09T08:13:28Z` |
| Observation | `obs-m14v3-base-1-20261109` |
| Observation quality | `degraded`: no related application event reported |
| Normalized evidence | 70 series, 1,750 raw samples |

The corrected generator returns 1 if any request worker records an exception or
if a worker remains active after the one-second shutdown grace. It emits no
per-request log, so the retained container evidence cannot distinguish those
two causes. The application error ratio was 0%; that does not exclude a
client-side timeout before the application produced a response. Weakening this
failure behavior or treating a failed Job as succeeded was outside the plan.

The evaluator extracted these descriptive A1 values:

| Measurement | A1 value |
| --- | ---: |
| Throughput | 12.6083 requests/second |
| Target attainment | 63.0417% |
| p95 latency | 0.489877 seconds |
| Mean throttled-period ratio | 79.5834% |
| Aggregate average CPU | 0.215270 cores |
| Throughput / average CPU | 58.5699 requests/second/core |
| p95 aggregate memory | 203,703,910.4 bytes |
| Error ratio | 0% |
| Ready ratio | 100% |
| Point-in-time cumulative restarts | 6 |

These values do not form a policy baseline and are not compared with a
candidate.

## Artifacts and policy result

| Artifact | SHA-256 |
| --- | --- |
| A1 experiment record | `e081f32a668adf2c713876a8646b775f823955b71552de1400e62f4faa2d8196` |
| A1 observation | `794e00bd8689aa2ac20e3cf52004d52d1f9451c90a4df7b58da0630fb4aa96cf` |
| Effectiveness report content | `017110aa7803111a4fc937d365b5d0f291247b5f030b524b2a1ce67e23725ca2` |
| Effectiveness envelope file | `2b79d7a56c7ed38581850fc7206d79acb61a653656c563491505a3be4463ee8e` |

The evaluator reported blocking issues for A1's non-succeeded lifecycle,
degraded measurement, insufficient repetitions, and incomplete required metric
comparisons. It produced no baseline/candidate means, differences, variation,
objective decisions, or guardrail decisions.

## Rollback, cleanup, and mutation scope

Rollback is **verified by unchanged baseline state**. No candidate apply
occurred, so a compensating Deployment apply was neither required nor allowed.
After cleanup:

- all four fixed v3 Job names are absent;
- A1 and its single owned Pod were deleted after evidence capture;
- no A2, B1, or B2 experiment or observation artifact exists;
- the original Deployment UID, resourceVersion, generation, image, resources,
  and 2/2 readiness are unchanged;
- `kri-workload-698f67d7f6` remains the sole application ReplicaSet at 2/2; and
- both original application Pod UIDs, runtime image IDs, readiness, and
  historical restart counts remain unchanged.

The only executed mutations were two approved baseline counter-initialization
HTTP requests, creation of the approved A1 Job and owned Pod, and deletion of
that Job and Pod. No Deployment, Service, monitoring object, namespace, image
cache, A2/B1/B2 Job, or unrelated resource was changed.

## Reproduce the offline evaluation

```bash
python scripts/evaluate_ab_experiments.py \
  --m14-plan evaluation/m14-local-cpu-limit-plan-v3.json \
  --m14-approval evaluation/m14-local-cpu-limit-approval-v3.json \
  --m14-trials evaluation/m14-local-cpu-limit-trials-v3.json \
  --report-id <new-report-id> \
  --rollback-status verified --cleanup-status verified \
  --output results/effectiveness/<new-report-id>.json
```

The retained report is immutable; reproduction must use a new ID and output.

## Diagnostic follow-up

After this immutable run, the load generator was updated without rerunning M14.
It now emits a schema-1.0 final JSON summary that separately counts request
failures, request timeouts, and workers still active after the shutdown grace.
Stable exits 2, 3, 4, and 5 identify request failure, timeout, stuck worker, and
multiple failure modes respectively. Load Pods use
`FallbackToLogsOnError`, allowing Kubernetes to preserve that final line in
container termination state. Exit 0 remains the only successful outcome, so
the evaluator's lifecycle guardrail is unchanged.
