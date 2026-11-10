# M14 local controlled experiment report v4

## Outcome

Plan `m14-kri-workload-cpu-limit-20261109-v4`, canonical digest
`30b702973e197b197d55919b18c4be690f8af8e8bdba98b8a6db859197aaad7c`,
was approved and all four fixed trials ran on 2026-11-09. Every load Job
completed normally with one Pod, zero restarts, the pinned cached image, exit
0, and exact schema-1.2 client evidence. All ten metric families were present
in every 120-second observation.

The authoritative M14 classification is **`inconclusive`**. Descriptively, the
220m candidate improved throughput, target attainment, latency, errors, and
memory, but failed two of three required objectives: throttling improved only
2.41% and remained above 0.60, while throughput per CPU core regressed 8.70%.
All five guardrails passed.

Two independent blockers prevent a causal policy decision:

- both baseline observations retained the limitation `no related events were
  reported`, which the unchanged evaluator treats as incomplete measurement;
- the candidate rollout emitted transient `Unhealthy` readiness warnings at
  `11:37:03Z` and `11:37:08Z`. The plan required stopping on any new warning,
  but that gate was not checked before B1 and B2 were run. Both candidate
  trials are therefore explicitly confounded and procedurally invalid.

The same transient probe pattern occurred during rollback at `11:46:08Z`
through `11:46:15Z`. The exact baseline configuration is restored and healthy,
but the plan required rollback verification with no new warning events.
Accordingly, the audited report records rollback `failed`, while cleanup is
`verified`. No further Kubernetes mutation was attempted.

## Trial evidence

| Trial | Requests completed / succeeded | Timeouts | Other failures | Stuck | Observation quality |
| --- | ---: | ---: | ---: | ---: | --- |
| A1 `m14v4-base-1-20261109` | 1,465 / 1,462 | 3 | 0 | 0 | degraded: no related event reported |
| A2 `m14v4-base-2-20261109` | 1,544 / 1,541 | 3 | 0 | 0 | degraded: no related event reported |
| B1 `m14v4-cand-1-20261109` | 2,057 / 2,054 | 3 | 0 | 0 | complete; rollout warning declared separately |
| B2 `m14v4-cand-2-20261109` | 2,072 / 2,070 | 2 | 0 | 0 | complete; rollout warning declared separately |

For every trial, requests started equaled requests completed, stdout equaled
the Kubernetes termination message, and the schema-1.2 experiment
`load_summary` equaled that termination evidence. Client timeouts remained
measured failures under the error guardrail without failing the Job.

Each observation retained 70 normalized/raw source series. Sample counts were
1,750 for A1, A2, and B2 and 1,747 for B1. Metrics intervals were exactly the
120 seconds from each reconciled Kubernetes Job start.

## Effectiveness results

| Metric | Baseline mean | Candidate mean | Relative change | Decision |
| --- | ---: | ---: | ---: | --- |
| Throughput (requests/s) | 12.1000 | 17.0109 | +40.59% | descriptive |
| p95 latency (s) | 0.54356 | 0.41584 | -23.50% | guardrail passed |
| Throttled-period ratio | 0.81614 | 0.79646 | -2.41% | objective failed: requires -20% and <=0.60 |
| Average CPU (cores) | 0.22375 | 0.34527 | +54.31% | descriptive |
| p95 memory (bytes) | 196,316,364.8 | 167,811,072.0 | -14.52% | guardrail passed |
| Error ratio | 0.1995% | 0.1212% | -39.27% | guardrail passed; both <=1% |
| Ready ratio | 100% | 100% | 0% | guardrail passed |
| Restarts | 6 | 0 | -100% | guardrail passed; baseline is historical cumulative state |
| Target attainment | 0.6050 | 0.85055 | +40.59% | objective passed |
| Throughput / CPU core | 54.0671 | 49.3608 | -8.70% | objective failed: must not regress |

All results retain two individual values per role plus population standard
deviation in the machine report. They do not establish a production confidence
interval. Because the classification is `inconclusive`, the descriptive
objective failures must not be promoted to a causal recommendation decision.

## Rollback and cleanup

The approved rollback apply restored Deployment UID
`3360fb27-d522-4b1d-9774-aa9e359e301a` to CPU `90m/140m`, memory
`109Mi/192Mi`, two replicas, and the pinned application image. Generation is
3, reflecting the candidate and rollback applies. ReplicaSet
`kri-workload-698f67d7f6` is 2/2 and candidate ReplicaSet
`kri-workload-f89f88bf8` is 0/0. The two current baseline Pods are Ready with
zero restarts. Service UID/resourceVersion and spec remain unchanged.

All four V4 Jobs and owned Pods are absent. The node is Ready without pressure,
and Prometheus, cAdvisor, and both current application targets are healthy.
Cleanup is verified. Formal rollback verification is failed only because the
plan's no-new-warning criterion was not met; configuration restoration itself
is complete.

No Kubernetes mutation outside the enumerated Job, candidate rollout,
rollback, and owned-controller consequences occurred. However, running B1 and
B2 after the candidate warning events violated the plan's stop sequence and is
recorded rather than concealed.

## Retained artifacts

| Artifact | SHA-256 |
| --- | --- |
| Approval | `7180ef985c429f4c2aeb3b32ee73d960407c9aa589d5d8410300a53211085f49` |
| Initial four-trial manifest | `124ec74c6742b4cba140e0cac98df580f79e54e82f895b4a92846cd8335dfd5d` |
| Audited trial manifest | `e14bb17d74956995704f2d107d10f289252970b21dc07c3cb22b5f8ce756e9f6` |
| Preliminary evaluator envelope | `cdaa236cfc5812134dd31b58f3bcd40bf0574126de5981ce7de3fbba39499508` |
| Authoritative audited report content | `9b5da27b6f9eb254e72a4623ae2fdffbb82f59f9858644f7fff90d1826090f10` |
| Authoritative audited report envelope | `6645be759284aecfcaa1ffd4fbff27d473c11be435a4fb46440a277af6065dd3` |

The preliminary evaluator artifact is retained rather than overwritten. It
incorrectly marked rollback verified because it was generated before the final
warning-event audit. The separately named audited manifest/report supersede it.

## Reproduce the authoritative evaluation

```bash
.venv/bin/python scripts/evaluate_ab_experiments.py \
  --m14-plan evaluation/m14-local-cpu-limit-plan-v4.json \
  --m14-approval evaluation/m14-local-cpu-limit-approval-v4.json \
  --m14-trials evaluation/m14-local-cpu-limit-trials-v4-audited.json \
  --report-id <new-report-id> \
  --rollback-status failed --cleanup-status verified \
  --output results/effectiveness/<new-report-id>.json
```

The retained report is immutable; reproduction must use a new report ID and
output path.
