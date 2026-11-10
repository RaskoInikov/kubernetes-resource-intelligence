# M14 local controlled experiment report

## Outcome

Execution was explicitly approved on 2026-11-08 for plan
`m14-kri-workload-cpu-limit-20261106`, digest
`612af134d27a524e300c6f80e36c4367b5060a3ed10d7ab34f6a90d75130062e`.
The run stopped at the first mandatory stop condition. Baseline trial A1 failed
its Kubernetes Job deadline, so A2, the candidate rollout, B1, and B2 were not
started.

The M14 classification is **`inconclusive`**. No candidate configuration was
deployed, so the plan's throttling, target-attainment, CPU-efficiency, latency,
error, readiness, restart, and memory comparisons cannot be evaluated. This is
not evidence that the `220m` candidate is effective or ineffective.

## A1 lifecycle and observation

| Field | Recorded value |
| --- | --- |
| Experiment | `m14-base-1-20261106` |
| Job UID | `6676ff20-1b3c-4e14-a379-dc0365f4342b` |
| Kubernetes start | `2026-11-08T09:37:34Z` |
| Kubernetes terminal time | `2026-11-08T09:40:55Z` |
| State | `failed` |
| Reason | `DeadlineExceeded` |
| Message | `Job was active longer than specified deadline` |
| Exact metrics interval | `2026-11-08T09:37:34Z` through `2026-11-08T09:39:34Z` |
| Observation | `obs-m14-base-1-20261106` |
| Observation quality | `degraded`: no related events were reported |
| Normalized evidence | 70 series, 1,750 samples |

The configured 120-second mixed load used concurrency 4 and target 20
requests/second. The Job manifest's fixed deadline is 180 seconds; Kubernetes
eventually recorded the failed transition 201 seconds after its start. The
container produced no retained load summary before termination.

Offline diagnosis on 2026-11-09 reproduced the lifecycle failure: a 50 ms run
with one non-returning request was still alive after 500 ms and required
termination. The scheduler stopped admitting requests at its deadline, but its
`ThreadPoolExecutor` context then called `shutdown(wait=True)`. Python also joins
executor workers during interpreter shutdown. A request stuck beyond its
nominal socket timeout could therefore hold the process indefinitely, which is
why Kubernetes, rather than the load generator, supplied A1's terminal state.
The retained evidence does not identify the exact network operation that
stalled, but no other load-generator path could block beyond the configured
deadline.

The fix replaces executor-owned workers with a concurrency-bounded set of
daemon request threads. It stops admission at the same duration deadline,
allows completed work a fixed one-second drain, and exits nonzero if a request
is still active. No resource recommendation, M14 threshold, plan value, or
retained experiment artifact changed. The M14 experiment was not rerun.
The stuck-request reproduction now exits independently after approximately
1.1 seconds with status 1, and the complete offline verification suite passes.

A separate, non-M14 lifecycle smoke experiment verified the corrected image in
the local kind cluster on 2026-11-09. Job
`kri-load-lifecycle-smoke-20261109` used image
`kri-workload:lifecycle-smoke-20261109` (runtime digest
`import-2026-11-09@sha256:c0cd3e143d5bb04237340cdea0bc14b0709cce17911152a34faa375bc7e5889e`),
mixed load at 5 requests/second with concurrency 2, a 10-second duration, and a
70-second active deadline. Its container ran from `2026-11-09T07:31:57Z` to
`2026-11-09T07:32:08Z`, exited 0 with no restart, and the Job reached
`Complete`/`CompletionsReached` at `2026-11-09T07:32:11Z`. The disposable Job
was then deleted. The application Deployment retained UID/resourceVersion
`3360fb27-d522-4b1d-9774-aa9e359e301a`/`1195095`, generation 1,
`kri-workload:local`, CPU `90m/140m`, and 2/2 readiness. No M14 A/B trial or
candidate rollout was started.

The read-only evaluator extracted these A1 measurements while preserving the
failed lifecycle and observation limitation:

| Measurement | A1 value |
| --- | ---: |
| Throughput | 11.5583 requests/second |
| Target attainment | 57.7917% |
| p95 latency | 0.611648 seconds |
| Mean throttled-period ratio | 86.3178% |
| Aggregate average CPU | 0.211680 cores |
| Throughput / average CPU | 54.6029 requests/second/core |
| Error ratio | 0% |
| Ready ratio | 100% |
| Point-in-time cumulative restarts | 6 |

These single-baseline values are descriptive only. The report does not compute
an effect from them.

## Policy result

Report `m14-kri-workload-cpu-limit-20261108` has SHA-256
`9ee9834a4065060d39fdfcf8cb3a62110326a7b3473219d1c00637dd1bc87f1d`.
Blocking issues are:

- A1 did not have a succeeded terminal lifecycle;
- A1 retained an observation-quality limitation;
- the plan lacks its second baseline and both candidate repetitions; and
- every objective/guardrail metric lacks a complete two-baseline/two-candidate
  comparison.

Rollback and cleanup are independently `verified`. No rollout occurred, so the
original workload remained in place rather than requiring a compensating
rollout.

## Restoration and cleanup

Only Job `kri-load-m14-base-1-20261106` was created. Its terminal experiment
record and immutable observation were saved before the Job was explicitly
deleted. No A2, B1, or B2 Job exists.

Deployment `payments/kri-workload` remains:

- UID `3360fb27-d522-4b1d-9774-aa9e359e301a`;
- resourceVersion `1195095`, generation 1;
- two replicas;
- CPU request/limit `90m/140m`; and
- memory request/limit `109Mi/192Mi`.

The local Prometheus port-forward remains available; it is not a Kubernetes
resource mutation.

## Reproduce the offline evaluation

```bash
python scripts/evaluate_ab_experiments.py \
  --m14-plan evaluation/m14-local-cpu-limit-plan-v1.json \
  --m14-approval evaluation/m14-local-cpu-limit-approval-v1.json \
  --m14-trials evaluation/m14-local-cpu-limit-trials-v1.json \
  --report-id m14-kri-workload-cpu-limit-20261108 \
  --rollback-status verified --cleanup-status verified \
  --output results/effectiveness/m14-kri-workload-cpu-limit-20261108.json
```

The output path is immutable. Reproduction must use a new report ID/output or
first compare the existing retained report rather than overwriting it.
