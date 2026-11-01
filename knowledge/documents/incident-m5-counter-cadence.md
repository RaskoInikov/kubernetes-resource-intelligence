# Incident: M5 Counter Cadence Inflated CPU Peaks

## Classification

Historical project incident. Resolved in analyzer and policy version 1.1 on
2026-11-01.

## Recorded evidence

The saved real M3 observation used five-second Prometheus range evaluations over
source values that updated at a slower scrape cadence. Repeated counter values
were followed by one accumulated increment. Treating that increment as a
five-second adjacent rate inflated per-Pod CPU peaks to 334m and 286m even though
the configured limit was 100m.

The same observation contained independent strong quota evidence: throttled CFS
period ratios were 87.09% and 85.88%. Average CPU was 98.01m and 82.10m.

## Resolution

- Coalesce repeated counter evaluations for peak calculation.
- Exclude the first potentially partial counter update when later update
  intervals are available.
- Record scrape-cadence uncertainty in the analysis report.
- Use condition-specific critical thresholds instead of comparing every ratio
  with 1.0.

The corrected peaks were 126m and 95m. The bounded CPU-limit recommendation
changed from 200m to 160m. Seven conditions remained supported, with corrected
severity and rationale, and the report retained explicit uncertainty.

## Lessons

Prometheus query-range timestamps are evaluation times, not proof of new source
scrapes. Peak counter rates require cadence awareness; total-window averages and
total-delta throttling ratios are less sensitive to repeated evaluations.
