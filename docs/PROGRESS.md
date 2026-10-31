# Project Progress

## Current milestone
M1 — Disposable application and workload control (complete and kind-verified)

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

## Next
M2 — Prometheus monitoring infrastructure.

## Known limitations
- The cluster Metrics API was unavailable during M1 verification; load evidence
  used application process CPU and network receive counters instead.
- The verified workload image remains cached on the disposable kind node.
- Monitoring, collectors, analysis, knowledge retrieval, API, and frontend are
  not implemented yet.
