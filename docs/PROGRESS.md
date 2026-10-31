# Project Progress

## Current milestone
M2 — Prometheus monitoring infrastructure (complete and kind-verified)

## Completed
- Git repository initialized.
- Initial architecture and project requirements defined.
- Installable Python 3.12+ package and `src` repository layout created.
- Runtime and development dependencies declared with bounded major versions.
- Environment-based configuration added with required-value and URL validation.
- Offline configuration tests cover successful and failure behavior.
- Ruff, mypy, pytest, branch coverage, and aggregate verification commands added.
- M0 acceptance criteria and developer setup documented.
- Versioned workload, load, and experiment lifecycle contracts implemented.
- Hardened disposable HTTP application and rate-controlled load image added.
- Configurable Deployment and Service rendering implemented.
- Independent per-experiment load Jobs and atomic JSON records implemented.
- Scoped `kubectl` controller and explicit workload CLI implemented.
- M1 safety boundary, acceptance criteria, and operator workflow documented.
- Thread-safe Prometheus HTTP counters, error counters, and latency histogram
  added to the disposable application at `/metrics`.
- Workload Pods annotated for direct per-Pod scraping.
- Project-owned disposable Prometheus, read-only discovery RBAC, cAdvisor metric
  filtering, bounded resources, and six-hour ephemeral retention added.
- Canonical PromQL added for CPU, throttling, memory, throughput, errors, and
  latency without missing-value substitution.
- M2 acceptance criteria, source-series units, architecture, and operator
  procedure documented.

## Verification

- `make verify`: passed for M0 on 2026-10-31.
- M1 `make verify`: passed on 2026-10-31 with Ruff formatting/linting,
  strict mypy, and 49 offline pytest cases at 100% branch coverage.
- `kri-workload --help` passed from the editable installation.
- `docker build --tag kri-workload:local deploy/workload` passed, followed by
  a network-disabled, read-only container smoke test.
- Real-service M1 verification passed on 2026-10-31 against context
  `kind-kube-optimizer`, namespace `payments`, using image ID
  `sha256:37a4aa85a58f...` and experiment `exp-m1-verify-20261031`.
- The application reached 2/2 ready replicas with zero restarts. During the
  mixed 10 requests/second load, per-pod CPU ticks and received bytes increased,
  while the Job and its persisted lifecycle record remained `running`.
- Job-only stop transitioned the record to `stopped` after 31 seconds and left
  the Deployment and Service UIDs/resourceVersions unchanged at 2/2 ready.
- Cleanup removed every M1-owned Deployment, Service, Job, and Pod. The existing
  `checkout` Deployment remained 3/3 ready.
- M2 offline verification passed on 2026-10-31 with 56 pytest cases and 100%
  branch coverage for the `kri` package; runtime and monitoring asset tests also
  passed.
- Rebuilt `kri-workload:local` image ID `sha256:4a3b066ee57a...` passed a
  read-only, network-disabled metrics smoke test.
- The pinned Prometheus `promtool` accepted the embedded configuration, and all
  nine Kubernetes resources passed a client dry-run against the kind cluster.
- Real-service M2 verification passed on 2026-10-31 against context
  `kind-kube-optimizer` with experiment `exp-m2-verify-20261031` and rebuilt
  workload image ID `sha256:4a3b066ee57a...`.
- Prometheus discovered two application targets and one cAdvisor target, all
  healthy. The 91.5-second experiment produced fresh, timestamped per-container
  CPU usage, CFS periods/throttling, memory working set, HTTP request/error, and
  latency histogram series at five-second evaluation steps.
- Verified aggregate values included 0.107 CPU cores, 80.1% throttled CFS
  periods, 27,656,192 working-set bytes, 4.2 requests/second, five controlled
  HTTP errors, and 0.887-second latency p95 at collection time.
- All range timestamps were strictly increasing and inside the recorded UTC
  experiment interval. Source samples were 0.84–3.99 seconds old when captured.
- Job-only stop preserved the 2/2-ready application. Cleanup removed all
  M1/M2-owned Kubernetes resources while the unrelated `checkout` and
  `kic-monitoring` workloads remained intact.

## Next
M3 — Kubernetes and Prometheus collectors.

## Known limitations
- The cluster Metrics API was unavailable during M1 verification; load evidence
  used application process CPU and network receive counters instead.
- The verified workload image remains cached on the disposable kind node.
- Python collectors, analysis, knowledge retrieval, API, and frontend are not
  implemented yet.
