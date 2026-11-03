# Product Definition

## Objective

Build a local, evidence-grounded Kubernetes resource intelligence system that:

- runs a disposable workload and collects real Kubernetes and Prometheus data;
- detects resource-related conditions with deterministic, traceable analysis;
- retrieves verified operational knowledge from Qdrant;
- explains the analysis with a local Qwen3 model without allowing model output
  to replace measured facts or deterministic recommendations;
- evaluates retrieval and recommendation effectiveness reproducibly; and
- exposes the complete workflow through FastAPI and a production-oriented
  React operator interface.

The intended user is an operator or developer investigating a bounded,
explicitly selected Kubernetes workload. The product supports diagnosis and
experimentation; it is not an autonomous remediation controller.

## Final User Experience

The final interface preserves the established two-column layout.

### Left: Workload and Experiment Control

- Configure CPU and memory requests and limits.
- Configure replica count.
- Configure load mode, concurrency, rate, and duration independently.
- Start, inspect, stop, and clean up disposable load experiments.
- Inspect lifecycle provenance and compare controlled experiment runs.
- View real CPU, throttling, memory, throughput, errors, and latency.

### Right: Evidence and Explanation

- Discover or collect immutable observation snapshots.
- Run deterministic analysis and inspect supporting measurements.
- Retrieve verified documentation, runbooks, and historical incidents.
- Build and inspect the validated LLM input package.
- Run local Qwen3 inference and inspect raw output, validation results,
  accepted claims, citations, and explicit rejection reasons.
- Compare reproducible RAG-on and RAG-off evaluations.
- Inspect recommendation-effectiveness reports, artifact history, and complete
  data lineage.

Long-running inference, evaluation, and experiment operations expose progress,
terminal status, cancellation where safe, and actionable dependency failures.
The browser presents backend-owned contracts and never performs analysis,
validation, retrieval, or Kubernetes calculations itself.

## Product Principles

- Monitoring values come from real systems, not generated examples.
- Missing data remains missing and is never silently replaced with zero.
- Raw observations, normalized signals, calculated statistics, retrieved
  evidence, model output, validation results, and human conclusions remain
  distinguishable.
- Deterministic Python logic owns numerical findings and resource values.
- Qdrant contains a rebuildable index; canonical knowledge remains versioned
  Markdown and JSON.
- Every explanation and evaluation remains traceable to timestamped source
  artifacts, exact model/index versions, settings, and content digests.
- Local LLM output is untrusted until an independent deterministic validator
  accepts its schema, references, numerical claims, and uncertainty coverage.
- Retrieval benefit is measured with paired, fixed-dataset RAG-on/off runs;
  unsupported claims and failed validations remain visible.
- Resource recommendations are evaluated only through bounded, approved,
  controlled experiments with explicit mutations and cleanup.
- Kubernetes resource changes always require explicit approval. No
  LLM-generated patch is applied directly and no recommendation is applied
  autonomously.
- Offline tests use recorded responses or deterministic doubles. Real-service
  verification is identified separately.

## Delivery Phases

M0–M11 are the completed foundation: disposable workload control, monitoring,
collectors, replayable observations, deterministic analysis, canonical
knowledge, Qdrant retrieval, validated LLM input, FastAPI, and a disposable
testing interface.

M12–M17 complete all backend, ML, retrieval, validation, controlled
experimentation, lineage, API, and reliability work. M18 cannot begin until
their acceptance criteria have verified evidence in `docs/PROGRESS.md`.

M18 replaces the disposable testing interface with the final
production-oriented React experience over the accepted backend contracts.

## Final Scope Boundary

The completed product ends at operator-reviewed, locally generated and
independently validated explanations plus reproducible retrieval and resource
effectiveness evaluations. It includes deployment-oriented frontend assets and
documented service boundaries.

Autonomous remediation, direct application of model-generated changes,
multi-cluster fleet management, model training or fine-tuning, managed-cloud
LLM dependencies, a web crawler, and a general-purpose observability platform
remain outside M18. Authentication, authorization, TLS termination, durable
multi-user scheduling, and backup policy belong to the external deployment
platform unless a later milestone explicitly brings them into scope.
