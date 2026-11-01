# Kubernetes Resource Intelligence

Kubernetes Resource Intelligence is an evidence-grounded resource analysis
project. M1 provides a disposable application and independently controlled load;
M2 adds Prometheus monitoring for container resources and HTTP behavior; M3
adds identity-bound, read-only Kubernetes and Prometheus collectors; M4 creates
replayable observations; M5 produces deterministic, evidence-linked resource
analysis and bounded recommendations; and M6 adds canonical verified knowledge.

## Requirements

- Python 3.12 or newer
- A virtual environment tool (`venv` is sufficient)

No Kubernetes cluster or external service is needed for offline verification.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
cp .env.example .env
```

`.env` is for local values and is not committed. Settings use the `KRI_`
prefix and fail validation when a required value is absent or malformed.

## Verification

Run the complete local verification suite:

```bash
make verify
```

The individual commands are:

```bash
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pytest --cov=kri --cov-report=term-missing
```

These checks are offline. Future real-service checks must be reported
separately, as required by `AGENTS.md`.

## Repository layout

- `src/kri/` — Python contracts, collectors, observations, analysis, and workload
  controller.
- `tests/` — offline Python tests.
- `deploy/workload/` — build context for the disposable target/load image.
- `deploy/monitoring/` — disposable Prometheus resources and canonical PromQL.
- `knowledge/` — canonical Markdown knowledge and its versioned integrity
  manifest.
- `results/` — generated experiment artifacts (ignored except `.gitkeep`).
- `web/` — future frontend application.
- `docs/` — product, architecture, contracts, roadmap, and progress.

See `docs/ROADMAP.md` for milestone scope. Do not implement later milestones
as part of repository setup.

## M1 workload operations

All commands target `KRI_K8S_CONTEXT` and the pre-existing
`KRI_K8S_NAMESPACE`. The controller never creates a namespace. Build the test
image and make it available to the target cluster using the mechanism for that
cluster. For the example kind context:

```bash
make workload-image IMAGE=kri-workload:local
kind load docker-image kri-workload:local --name kube-optimizer
```

Building or loading an image changes local Docker or cluster-node state. Run
those commands only as an explicitly approved experiment operation.

Application deployment is separate from load generation:

```bash
kri-workload deploy \
  --cpu-request 100m --cpu-limit 500m \
  --memory-request 64Mi --memory-limit 256Mi \
  --replicas 2

kri-workload start-load \
  --cpu-request 100m --cpu-limit 500m \
  --memory-request 64Mi --memory-limit 256Mi \
  --replicas 2 \
  --mode mixed --concurrency 4 --request-rate 10 \
  --duration-seconds 60 --experiment-id exp-example-1

kri-workload status exp-example-1
kri-workload stop-load exp-example-1
kri-workload delete
```

`stop-load` deletes only `job/kri-load-<experiment-id>`. It does not modify the
Deployment or Service. `delete` is the distinct application-removal operation.
Experiment records are written atomically beneath `results/experiments/` and
are ignored by Git.

The request rate is a target, not an unbounded queue. If all configured workers
are occupied, scheduled arrivals are skipped. New requests stop at the duration
deadline and in-flight request timeouts cannot extend beyond the remaining
experiment time.

These commands perform persistent Kubernetes mutations and therefore require
explicit approval before execution. M1's default `make verify` is fully offline
and uses fake command responses. Optional real-cluster verification must record
the context, namespace, image, commands, and observed results separately; mock
or dry-run results must not be reported as real integration success.

## M2 Prometheus monitoring

The application exposes `/metrics` with request totals, error totals, and a
request-duration histogram. Its Pod template carries explicit Prometheus scrape
annotations. The monitoring manifest installs a separate, project-owned
Prometheus in `kri-monitoring` and grants read-only access to:

- annotated `kri-workload` Pods in `payments`;
- node discovery and kubelet cAdvisor through the API-server proxy.

The checked-in manifest targets the configured example namespace `payments`.
If `KRI_K8S_NAMESPACE` changes, update both namespaced RBAC resources and the
pod-discovery namespace before applying it.

The following commands are persistent Kubernetes mutations and require explicit
approval. They are shown as an operator procedure, not run by `make verify`:

```bash
make workload-image IMAGE=kri-workload:local
kind load docker-image kri-workload:local --name kube-optimizer
kubectl --context kind-kube-optimizer apply -f deploy/monitoring/prometheus.yaml
```

Deploy the M1 application and load as described above, then access Prometheus:

```bash
kubectl --context kind-kube-optimizer \
  --namespace kri-monitoring port-forward service/kri-prometheus 9090:9090
```

Canonical queries for CPU usage, throttling, memory working set, throughput,
errors, and latency p95 are in `deploy/monitoring/queries.md`. An empty result is
missing data and must not be treated as zero.

Cleanup removes only project-owned monitoring resources:

```bash
kubectl --context kind-kube-optimizer delete -f deploy/monitoring/prometheus.yaml
```

The monitoring Namespace uses ephemeral storage and the Prometheus image remains
cached on kind nodes after cleanup.

## M3 read-only collection

`KubernetesCollector` captures the fixed disposable Deployment, matching Pods,
configured resources, readiness/restarts, and related events. `KubectlReader`
issues only `get` commands and always supplies `KRI_K8S_CONTEXT` and
`KRI_K8S_NAMESPACE`. The resulting Deployment UID is the workload identity used
for the matching `PrometheusCollector` snapshot.

The Prometheus collector performs only `/api/v1/query_range` requests. Callers
provide a timezone-aware start/end interval and a Kubernetes snapshot so every
query is restricted to its namespace, workload job, application container, and
Pod names. Returned data remains raw: source labels, units, timestamps, and
values are preserved. Empty expected metric families produce `missing_data`
entries; they never produce zero-valued samples.

Collection is available as a Python API in `kri.collectors`. It does not deploy,
modify, normalize, aggregate, or persist observations; normalization and
storage belong to M4. Offline tests use fake source responses. Any claim of
real-service collection must be verified and reported separately.

The opt-in real-service verifier is `scripts/verify_m3_collectors.py`. It writes
the complete versioned Kubernetes and raw Prometheus snapshots beneath
`results/m3-verification/`; those generated artifacts are intentionally ignored.

## M4 observations

`ObservationBuilder` combines identity-matched M3 snapshots into a versioned
`ObservationSnapshot`. The artifact embeds both raw inputs, adds a separate
canonical normalized view, records structured quality issues, and hashes the
raw provenance. Normalization preserves source timestamps and values; it does
not calculate rates or other M5 statistics.

`ObservationStore` saves immutable JSON artifacts atomically beneath a caller-
selected directory, returns bounded summaries from `inspect`, and uses `replay`
to rebuild normalized data and quality from embedded raw inputs. Loading rejects
malformed artifacts or raw-source digest mismatches; replay also rejects changes
to normalized series, quality, or provenance.

```python
from pathlib import Path
from kri.observations import ObservationBuilder, ObservationStore

snapshot = ObservationBuilder().build(workload_snapshot, raw_metrics_snapshot)
store = ObservationStore(Path("results/observations"))
store.save(snapshot)
summary = store.inspect(snapshot.observation_id)
replayed = store.replay(snapshot.observation_id)
```

## M5 deterministic analysis

`DeterministicAnalyzer` accepts an M4 snapshot only after replay validation. It
calculates per-Pod/container CPU, throttling, and memory statistics plus
workload-level HTTP context, applies policy version `1.0`, and returns a
versioned `AnalysisReport`. Every finding and recommendation links back to exact
normalized-series and workload-configuration evidence.

```python
from pathlib import Path
from kri.analysis import DeterministicAnalyzer
from kri.observations import ObservationStore

store = ObservationStore(Path("results/observations"))
report = DeterministicAnalyzer().analyze_saved(store, "obs-example")
```

Counter resets and missing inputs suppress dependent results; they are never
repaired or replaced with zero. Repeated counter evaluations are coalesced for
CPU peak rates when the query step is finer than scrape cadence. Recommendations
only increase resources, round to Kubernetes units, remain at or below
configured limits where applicable, never exceed twice the current value, and
always require explicit approval. Reports retain finite-window, scrape-cadence,
near-threshold, and constrained-headroom uncertainty. M5 is read-only and
performs no Kubernetes mutation.

## M6 canonical knowledge

`knowledge/manifest.json` registers the canonical Markdown corpus under
`knowledge/documents/`. It contains two Kubernetes references, two diagnostic
runbooks, and two historical project incidents. Every entry has a semantic
version, verification state, verifier and UTC timestamp, tags, explicit source
provenance, repository-relative path, and SHA-256 content digest.

`KnowledgeRepository` is a local read-only API. It validates the whole manifest,
safe path containment, exact checksums, matching top-level titles, complete type
coverage, and absence of unregistered Markdown before returning documents.

```python
from pathlib import Path
from kri.knowledge import KnowledgeRepository

repository = KnowledgeRepository(Path("knowledge"))
summaries = repository.inspect()
runbook = repository.get("runbook-cpu-throttling")
```

M6 does not contact Kubernetes, Prometheus, Qdrant, or the network. Qdrant
indexing, chunking, and retrieval are M7 concerns; generated vector state will
not replace the manifest and Markdown as canonical knowledge.
