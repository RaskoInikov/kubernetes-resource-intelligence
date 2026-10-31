# Kubernetes Resource Intelligence

## Objective

Build a Kubernetes workload analysis application that collects
real monitoring data, detects resource-related problems, and
uses RAG to support interpretable resource recommendations.

## User Experience

The application uses a two-panel interface.

### Left: Workload Control

Users can:
- Configure CPU/memory requests and limits.
- Configure replica count.
- Configure synthetic workload intensity and duration.
- Start and stop load generation.
- Observe real CPU, memory, throttling, throughput, and latency graphs.

Stopping load does not delete the application.

### Right: Analysis

Users can:
- Select an observation window.
- Enable or disable RAG.
- Trigger analysis manually.
- Review deterministic findings and recommendations.
- Inspect retrieved documents and supporting evidence.
- Inspect the prepared LLM input.

## Core Principles

- Experiments generate synthetic workloads but collect real metrics.
- Diagnosis is independent of predefined incident scenarios.
- Python calculates statistics and numerical recommendations.
- Qdrant retrieves supporting operational knowledge.
- RAG must improve interpretability and evidence grounding.
- Missing data must never be interpreted as zero.
- Resource changes require explicit approval.

## First Version Scope

The first development phase ends with a validated,
inspectable LLM input package.

LLM generation, automatic remediation, model training,
and production deployment are outside this phase.