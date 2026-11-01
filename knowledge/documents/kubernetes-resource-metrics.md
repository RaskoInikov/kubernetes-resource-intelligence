# Kubernetes Resource Metrics and Evidence Scope

## Scope

This reference describes how the project treats kubelet/cAdvisor and application
metrics when diagnosing Kubernetes resource behavior.

## Evidence rules

- Preserve cumulative counters as raw observations. Calculate rates only from
  positive deltas over explicit timestamp intervals.
- Treat a counter decrease as a reset unless source-specific evidence proves a
  different interpretation.
- Treat working-set memory as a gauge. Its mean, percentile, and maximum describe
  only the recorded interval and scrape resolution.
- Keep container labels and Pod identity attached to resource measurements.
  Deployment-level configuration may be compared with each matching container,
  but unrelated containers must not be aggregated into that comparison.
- A Prometheus range evaluation timestamp is not necessarily the original scrape
  timestamp. Query steps finer than scrape cadence can repeat values and make a
  single counter increment appear to occur over too short an interval.
- An empty result is missing evidence, not a zero measurement.

## Corroboration

Use multiple independent signals when available. CPU usage near a limit and a
high CFS throttled-period ratio support the same diagnosis through different
measurements. Memory working set should be considered with limits, restarts,
OOM events, and the observation window.

## Limitations

Metrics support bounded conclusions about their interval. They do not prove that
the same load, contention, or application behavior persists outside that window.
