# M14 V3 baseline failure diagnostic plan

Status: **prepared and unapproved; no Kubernetes mutation authorized**.

Plan ID: `m14-v3-baseline-diagnostic-20261109`

Execution requires a separate positive approval that quotes this plan ID and
the exact SHA-256 of this file reported in `docs/PROGRESS.md`. Any file change
invalidates that approval and requires a new digest and approval.

## Purpose and boundary

Run one bounded baseline load Job with the verified diagnostic image to
distinguish the failure modes that the immutable M14 V3 A1 evidence could not.
This is diagnostic traffic, not an M14 A/B trial, and its output must not be
added to an M14 trial manifest or used to decide recommendation effectiveness.

The run preserves the V3 baseline application configuration and original load
settings. It does not initialize error counters, collect a candidate
observation, apply a recommendation, or modify the application Deployment or
Service.

## Fixed identities and settings

| Item | Required value |
| --- | --- |
| Context / cluster | `kind-kube-optimizer` / `kind-kube-optimizer` |
| Namespace | `payments` |
| Application | Deployment and Service `kri-workload` |
| Application image | `docker.io/library/import-2026-10-31@sha256:ad6d70e96f19ec8472b41f2e135139da33c36fb1f22a83d23ce019f682807d91` |
| Baseline | 2 replicas; CPU `90m/140m`; memory `109Mi/192Mi` |
| Diagnostic ID | `m14v3-diag-base-20261109` |
| Job | `kri-load-m14v3-diag-base-20261109` |
| Diagnostic image reference | `kri-workload:diagnostics-20261109` |
| Pull policy | `Never` |
| Required runtime image ID | `docker.io/library/import-2026-11-09@sha256:7199ce4354f3c13ba9f82f114f8a9695ec309c8a88d2b0459301c6f49af6c052` |
| Load | mixed; concurrency 4; 20 requests/second; 120 seconds |
| Job controls | `backoffLimit: 0`; `activeDeadlineSeconds: 180`; restart `Never` |
| Load-container resources | requests `25m` CPU / `32Mi`; limits `500m` CPU / `128Mi` |
| Termination diagnostics | `FallbackToLogsOnError` |

The image was built from the updated source and verified in a one-second
real-cluster request-failure test. The node selected it from cache, Kubernetes
recorded exit 2, and the termination message exactly matched the final JSON
stdout line. This plan does not authorize rebuilding, retagging, pulling, or
loading any image.

## Mandatory read-only preflight

Immediately before requesting approval, and again immediately before
execution after approval, verify all of the following without mutation:

- the current context is exactly `kind-kube-optimizer` and namespace is
  `payments`;
- the application Deployment retains the pinned image, exact baseline
  resources, two desired/available/ready replicas, and no new restart;
- the application Service selector and port still target the same two ready
  Pods;
- the diagnostic image tag exists in the kind node inventory and resolves to
  the required runtime image ID;
- the fixed Job, any owned Pod, and local experiment record
  `results/experiments/m14v3-diag-base-20261109.json` are absent;
- the node is Ready without memory, disk, or PID pressure and has no new warning
  event;
- Prometheus is Ready and application/cAdvisor targets are healthy, preserving
  environmental comparability with V3 even though this diagnostic is not an
  effectiveness trial; and
- an offline render of the fixed load command matches every value in the table,
  including `imagePullPolicy: Never`, termination-message policy, limits,
  deadline, and target URL `http://kri-workload:8080/work`.

Stop before mutation on any mismatch. Do not repair drift under this plan.

## Exact execution after approval

The sole creation command is fixed:

```bash
KRI_WORKLOAD_IMAGE=kri-workload:diagnostics-20261109 \
  kri-workload start-load \
  --cpu-request 90m --cpu-limit 140m \
  --memory-request 109Mi --memory-limit 192Mi --replicas 2 \
  --mode mixed --concurrency 4 --request-rate 20 \
  --duration-seconds 120 \
  --experiment-id m14v3-diag-base-20261109
```

Wait only for this Job. It may run for the configured 120-second scheduling
window and must be terminal no later than its 180-second active deadline. Do
not retry or create a replacement Job. The Job controller may create exactly
one owned Pod.

After termination, perform read-only capture before cleanup:

1. retain the Job and Pod UID, timestamps, conditions, restart count, selected
   image reference, runtime image ID, and related events;
2. retain complete container stdout and the Kubernetes terminated state,
   including reason, exit code, and termination message;
3. parse exactly one final schema-1.0 JSON summary and require its `exit_code`
   to equal Kubernetes' exit code and its raw text to equal the termination
   message for a nonzero exit;
4. retain started, completed, succeeded, failed, timed-out, and stuck-worker
   counts without replacing missing values; and
5. record application Pod readiness/restarts and Deployment identity before
   and after the run.

Interpret the diagnostic exit without weakening lifecycle validation:

| Exit | Meaning | Diagnostic conclusion |
| ---: | --- | --- |
| 0 | `completed` | V3's failure is not reproduced; preserve this as a bounded non-reproduction, not proof of resolution. |
| 2 | `request_failure` | At least one non-timeout request exception caused failure. |
| 3 | `request_timeout` | At least one request timeout caused failure. |
| 4 | `stuck_worker` | At least one worker exceeded the bounded shutdown grace. |
| 5 | `multiple_failure_modes` | Two or more of request failure, timeout, and stuck worker occurred. |
| other / missing | invalid diagnostic | Preserve raw evidence and stop without inference. |

Any nonzero exit remains a failed Job. The diagnostic classification must not
be converted into an M14-valid lifecycle or used to relax evaluator guardrails.

## Exact Kubernetes mutations requiring approval

Approval authorizes only:

1. creation of the single namespaced Job
   `payments/kri-load-m14v3-diag-base-20261109` with the fixed specification
   above;
2. creation by the Job controller of exactly one Pod owned by that Job; and
3. deletion of that Job after evidence capture, allowing Kubernetes to
   garbage-collect only its owned Pod.

The 120-second request stream changes application metric counters and consumes
bounded application resources but is not a Kubernetes-resource mutation. It is
part of the approved diagnostic effect and targets only the existing
`kri-workload` Service.

No Deployment, ReplicaSet, application Pod, Service, ConfigMap, Secret,
namespace, monitoring resource, image cache, candidate Job, or M14 A/B trial
may be created, patched, restarted, scaled, deleted, or otherwise mutated.
Normal API-server metadata/status changes on the approved Job and owned Pod are
included. No candidate configuration or rollback apply is authorized because
the application must remain at baseline throughout.

## Stop, cleanup, and completion gates

Stop scheduling work and capture evidence if the Job fails, reaches its active
deadline, has more than one Pod, restarts, resolves the wrong image, or if the
application loses readiness, restarts, or drifts. These conditions do not
authorize remediation or another run.

After capture, delete only the fixed Job and verify the Job and owned Pod are
absent. Completion additionally requires the application Deployment UID,
generation, image, resources, replicas, and Pod readiness/restart state to
match the preflight. Report the diagnostic result as reproduced,
non-reproduced, or invalid, with raw counts and uncertainty. Candidate trials
remain prohibited regardless of outcome.
