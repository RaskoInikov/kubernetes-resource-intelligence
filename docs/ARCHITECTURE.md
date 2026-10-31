# Architecture

## Pipeline

1. Kubernetes workload and load generator.
2. Prometheus metrics collection.
3. Kubernetes API configuration and events.
4. Data normalization and quality validation.
5. Versioned observation snapshot.
6. Deterministic Python analyzer.
7. Qdrant knowledge retrieval.
8. LLM input package.
9. FastAPI and React presentation.

## Responsibilities

### Workload Controller
Creates and controls disposable Kubernetes experiments.

In M1 it renders a fixed-name application Deployment and Service and a unique
load Job. It invokes `kubectl` with an explicit context and namespace, persists
versioned experiment records as JSON artifacts, and never creates namespaces.
Stopping a load experiment deletes only its Job; application removal is a
separate operation. The target application and load generator share a small,
buildable test image but run as separate Kubernetes workloads.

### Prometheus Collector
Retrieves real workload time series.

M2 establishes collection infrastructure but not the M3 Python collector. A
project-owned Prometheus discovers annotated `kri-workload` Pods and scrapes
kubelet cAdvisor through the API-server node proxy. It retains only the required
container CPU/throttling/working-set series and the application's HTTP counters
and latency histogram. Storage is an ephemeral six-hour TSDB; no missing value
is generated or replaced with zero.

### Kubernetes Collector
Reads Deployment configuration, Pods, resources, and events.

### Observation Builder
Normalizes and validates collected information.

### Python Analyzer
Calculates statistics, findings, and bounded recommendations.

### Knowledge Repository
Maintains readable documentation, runbooks, and incidents.

### Qdrant Retriever
Retrieves relevant knowledge with source references.

### LLM Input Builder
Constructs concise, traceable input for a future LLM.

### FastAPI
Exposes workload, monitoring, analysis, and knowledge APIs.

### React
Provides workload controls, live graphs, and analysis views.

## Storage

- Prometheus: time series.
- Kubernetes API: live configuration and state.
- JSON artifacts: reproducible observations and experiments.
- Markdown/JSON: canonical knowledge.
- Qdrant: embeddings and searchable knowledge payloads.

No ClickHouse, crawler, or additional database.

## Project Foundation

- Python code is an installable `src/kri` package targeting Python 3.12+.
- Process configuration comes from `KRI_` environment variables, with `.env`
  supported only as a local-development convenience.
- Configuration validation happens before a component contacts an external
  service.
- Python collectors, observation building, analysis, retrieval, API, and
  frontend behavior remain outside M2.
