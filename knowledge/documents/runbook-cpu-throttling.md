# Runbook: Diagnose CPU Throttling

## Trigger

Use this runbook when CFS throttled periods are elevated, CPU usage approaches a
configured limit, latency rises under load, or CPU demand materially exceeds the
request.

## Required evidence

- Workload identity, Pod and container labels, and observation timestamps.
- Configured CPU request and limit.
- CPU usage counter, CFS periods, throttled periods, and throttled seconds.
- Request throughput, errors, and latency for workload context.
- Missing-data and counter-reset findings.

## Procedure

1. Confirm every series belongs to the same Deployment identity and container.
2. Calculate average CPU from the full positive counter delta and interval.
3. Calculate peak rates without treating repeated range evaluations as new
   scrapes. Exclude an initial partial update when later update intervals exist.
4. Calculate throttled-period ratio from total throttled-period and period deltas.
5. Compare average CPU with the request and peak CPU with the limit separately.
6. Correlate throttling with throughput and latency, but do not claim causation
   solely from temporal proximity.
7. If recommending a change, keep request at or below limit, apply bounded
   headroom, require approval, and record any cap that prevents the target.

## Interpretation

Increasing a CPU limit can reduce quota enforcement. Increasing a CPU request
improves scheduling representation and contention weight; it does not itself
remove a hard CPU limit. The two actions must not be presented as interchangeable.

## Verification and rollback

Run a bounded comparable load after an approved change. Verify throttling,
throughput, errors, latency, and restarts. If behavior regresses or evidence is
incomplete, restore the previous configuration and retain both observations.
