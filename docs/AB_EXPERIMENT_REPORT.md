# A/B workload resource experiment evaluation

This report replays the retained, immutable observations through the M5 deterministic analyzer. It does not query Kubernetes or Prometheus. Artifact cutoff: `2026-11-02T16:26:22.912952+00:00`.

## Reproduce

```console
python scripts/evaluate_ab_experiments.py \
  --baseline-experiment results/experiments/exp-41127021a11e.json \
  --baseline-observation results/observations/obs-ui-20261102154751.json \
  --candidate-experiment results/experiments/exp-67edfb4c355c.json \
  --candidate-observation results/observations/obs-ui-20261102161957.json \
  --output docs/AB_EXPERIMENT_REPORT.md
```

Input integrity:

- A experiment `exp-41127021a11e`: `19128a0963f81414c7fd679c398ed061cfe2022a4cac416afe952c5431b794d7`
- A observation `obs-ui-20261102154751`: `2a064826030bd1685bbc69516adc111473f240454bdf907a5447ae4eea93f3d4`
- B experiment `exp-67edfb4c355c`: `b2c918f2a6dcac5fa8fdce78e40514181370f23e7f19451afeac344329430254`
- B observation `obs-ui-20261102161957`: `4fc81d13339905c044e03cae800d4caa6196905c22f5a5621bea7172e53564a2`

## Experiment controls

Both records specify `mixed` load, concurrency 4, target 20 requests/s, duration 120 seconds, and 2 replicas. B changed CPU request from 50m to 90m, CPU limit from 100m to 140m, and memory request from 64Mi to 109Mi; the 192Mi memory limit was unchanged.

The paired observations have matching recorded resource values, but different Deployment UIDs: `45768e85-db0d-4b6e-8b80-221d0b39f494` for A and `3360fb27-d522-4b1d-9774-aa9e359e301a` for B.

## Results

| Measurement | A baseline | B candidate | B - A | Relative change |
| --- | ---: | ---: | ---: | ---: |
| Actual `/work` throughput | 9.030 req/s | 12.525 req/s | +3.495 req/s | +38.70% |
| `/work` histogram p95 | 888.179 ms | 592.416 ms | -295.764 ms | -33.30% |
| Aggregate average CPU | 143.300 mCPU | 223.855 mCPU | +80.555 mCPU | +56.21% |
| Highest per-Pod CPU peak | 109.638 mCPU | 175.053 mCPU | +65.415 mCPU | +59.66% |
| Mean throttled-period ratio | 84.97% | 84.50% | -0.464 pp | -0.55% |
| Aggregate throttled CPU seconds/s | 1.573 | 1.534 | -0.039 | -2.50% |
| Response-code-derived error rate | 0.00% | 0.00% | +0.000 pp | n/a (zero baseline) |

Throughput attainment improved from 45.15% to 62.62% of the configured target (+17.475 percentage points), but B still did not sustain the 20 req/s target. The extra CPU was consumed: average aggregate CPU rose 56.21%. Despite that, throttling frequency was effectively unchanged and remained extreme.

## Workload stability

| Indicator | A baseline | B candidate |
| --- | ---: | ---: |
| Ready Pods at collection | 2/2 | 2/2 |
| Container restarts at collection | 0 | 0 |
| Warning events timestamped inside metrics interval | 0 | 0 |
| Observed `/work` request delta | 903 | 1471 |
| Observed non-2xx/3xx request delta | 0 | 0 |
| Observation quality | `degraded` | `degraded` |

Both snapshots show 2/2 ready Pods, zero restarts, no warning event timestamped inside the metric window, no counter-reset quality finding, and only HTTP 200 `/work` request series. This supports short-window server-side stability. It does not prove load-generator completion or client-side success.

## Calculation notes

- Throughput is the sum of per-Pod `(last counter - first counter) / elapsed sample time` for `http_requests_total{route="/work"}`.
- p95 is M5's interpolation over the aggregate delta of cumulative `/work` histogram buckets; it is an estimate bounded by the exported buckets.
- Aggregate average CPU is the sum of M5 per-Pod average rates from `container_cpu_usage_seconds_total`. Pod peaks are not summed because their timestamps need not align.
- Throttle frequency is the arithmetic mean of per-Pod throttled-period ratios. Throttled CPU seconds/s is summed across the two Pods.
- The response-code error rate uses non-2xx/3xx deltas divided by all observed `/work` request deltas. It is shown separately from the missing contractual error counter.

## Data-quality limitations

- Both observations are `degraded`: `kri_http_request_errors_total` returned no series. All observed request-status series are HTTP 200, giving a response-code-derived 0% rate, but the required error signal is not independently verified. Missing data is not treated as zero: dedicated-counter error rate remains unavailable (confirmed missing in both snapshots: true).
- Each metrics query spans 120 seconds, but `/work` counter coverage is 100-100 seconds for A and 115-120 seconds for B. The experiment/metrics-window overlaps are 107.195 seconds and 117.365 seconds respectively; A starts observing before load starts and omits the nominal final segment.
- Both experiment records still say `running` and have no end timestamp, even though their configured durations elapsed before observation creation. Therefore completion, duration adherence, stop behavior, and load-generator client failures cannot be verified from these records.
- Pod readiness and restart counts are point-in-time Kubernetes observations, not continuous availability measurements. Event absence is limited by event collection and retention.
- B changes CPU request, CPU limit, and memory request together. The experiment cannot isolate which change caused the throughput/latency result. Resource requests affect scheduling, while the CPU limit directly changes available CPU.
- The records do not capture the application/load image digest or node conditions, so unchanged binaries and an otherwise identical environment cannot be proven.
- Observations do not carry an experiment ID. Pairing is based on matching resource values and overlapping timestamps, not an explicit artifact foreign key; the different Deployment UIDs confirm separate deployments.
- This is one sequential A/B pair with no repeated or randomized trials. The numerical difference is real for these saved windows but has no confidence interval and should not be generalized as a causal effect size.

## Conclusion

For the retained observations, B is directionally better: `/work` throughput is +38.70% and p95 latency is -33.30%, with ready Pods, zero restarts, and no observed non-success response codes in both snapshots. The gain costs +56.21% more average CPU. Mean throttled-period ratio changes only -0.464 percentage points and remains 84.50%, while throughput reaches only 62.62% of target.

The evidence supports retaining B as the better of these two tested configurations, but not declaring the resource problem solved. A synchronized post-change experiment with terminal lifecycle records, the dedicated error series, load-generator summary, immutable image digests, and repeated trials is needed before treating the effect as validated or adopting a further CPU increase.
