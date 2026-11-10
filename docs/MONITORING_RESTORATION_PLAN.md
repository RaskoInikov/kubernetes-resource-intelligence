# Local Prometheus access restoration

Status: **local access restored and verified** at `2026-11-06T14:36:41Z`.
No Kubernetes object was changed and no load experiment was created. A
foreground process forwards only `127.0.0.1:9090` to the existing Service.

## Diagnosis

Prometheus is not unavailable inside Kubernetes. The failure is limited to the
host-side access path expected by `KRI_PROMETHEUS_URL=http://localhost:9090`.

- Namespace `kri-monitoring` is Active. The ServiceAccount, cluster and
  namespaced RBAC, ConfigMap, Deployment, and Service all exist.
- Every live object matches `deploy/monitoring/prometheus.yaml`, whose SHA-256
  is `4e789d0b0d9ff4b5eea92a6f2ebaf5313744e2df560f45bf04b9cc93a5530de3`.
- Deployment `kri-prometheus` is generation 1 and 1/1 Ready/Available. Its Pod
  is Ready and runs the manifest's pinned image digest
  `sha256:8672a850efe2f9874702406c8318704edb363587f8c2ca88586b4c8fdb5cea24`.
- Service `kri-prometheus` has endpoint `10.244.0.12:9090`. The API-server
  Service proxy returns `Prometheus Server is Ready.`
- Prometheus reports four healthy active targets: itself, cAdvisor, and both
  `payments/kri-workload` Pods. Current cAdvisor CPU, throttling, and memory
  selectors each return two series.
- At diagnosis time nothing listened on host port 9090 and no
  `kubectl ... port-forward` process existed. Because the Service is
  `ClusterIP`, `localhost:9090` refused connections without that process.

The earlier M14 preflight queried namespace `monitoring`, not the actual
`kri-monitoring` namespace, and incorrectly described the monitoring resources
as absent. This document and the M14 plan now supersede that diagnosis.

The Prometheus Pod has three historical restarts; its most recent prior state
ended with `Unknown`/255 at `2026-11-04T11:08:51Z`, coincident with other local
kind workload restarts. It has been Running and Ready since
`2026-11-04T11:09:00Z`, has no retained warning events, and is not the cause of
the current connection refusal.

At initial inspection, no `/work` request, error, or latency series existed for
the restarted application Pods because they had received no `/work` request
since restart. That was an experiment measurement-readiness issue, not a scrape
failure, and was not treated as zero. The bounded initialization recorded below
made those families observable outside any M14 measurement window.

## Verification record

The existing loopback port-forward was reverified for M14 V4 at
`2026-11-09T11:23:36Z`; no replacement process was needed. Prometheus reported
Ready, and its four expected targets (Prometheus, cAdvisor, and both application
Pods) were `up` without a last error. A 30-second no-load range at 5-second
steps returned all ten required M14 families: 42 series and 294 finite samples,
with seven samples per series. Monitoring Deployment UID/resourceVersion/
generation and Service UID/resourceVersion remained
`df8ac41f-3113-4010-98e3-276d31aa8a9a`/`1154524`/`1` and
`0175f190-74cb-48b9-8209-5ea8fcd2e240`/`1154489`; workload Deployment
UID/resourceVersion/generation remained
`3360fb27-d522-4b1d-9774-aa9e359e301a`/`1195095`/`1`. No load Job existed,
no diagnostic request was sent, and no Kubernetes object was modified.

The restoration followed the procedure below without applying the manifest.
To initialize otherwise absent HTTP families, each application Pod received
exactly one zero-work successful request (`cpu_ms=0`, `memory_mb=0`) and one
bounded invalid request (`cpu_ms=1001`, `memory_mb=0`, HTTP 400). These four
diagnostic requests occurred before any M14 experiment window; no load Job was
created.

After two scrape intervals, a 20-second range query returned five samples per
series for both application Pods:

| M14 source family | Series | Samples per series |
| --- | ---: | ---: |
| CPU usage counter | 2 | 5 |
| CPU CFS periods counter | 2 | 5 |
| CPU throttled periods counter | 2 | 5 |
| CPU throttled seconds counter | 2 | 5 |
| Memory working set | 2 | 5 |
| `/work` request counter | 4 | 5 |
| `/work` error counter | 2 | 5 |
| `/work` latency histogram buckets | 22 | 5 |

Prometheus, cAdvisor, and both application scrape targets remained `up` with no
last error. Monitoring Deployment resourceVersion remained `1154524`; workload
Deployment resourceVersion remained `1195095`, generation 1, with CPU limit
`140m`. No M14 experiment Job exists. The initialized counters must not be
included in a future experiment interval; range calculations must start after
this verification record.

## Minimal restoration: no Kubernetes resource changes

Do not apply the manifest. The minimal restoration is one foreground,
loopback-only port-forward using the existing Service. It creates no Kubernetes
resource and is removed by terminating the local process.

First repeat these read-only guards:

```bash
kubectl config current-context
kubectl --context kind-kube-optimizer --namespace kri-monitoring \
  get deployment/kri-prometheus service/kri-prometheus
kubectl --context kind-kube-optimizer --namespace kri-monitoring \
  get endpointslice \
  --selector kubernetes.io/service-name=kri-prometheus
kubectl --context kind-kube-optimizer get --raw \
  '/api/v1/namespaces/kri-monitoring/services/http:kri-prometheus:9090/proxy/-/ready'
ss -ltnp 'sport = :9090'
```

Proceed only when the context is `kind-kube-optimizer`, the Deployment is 1/1
Ready, the endpoint is populated, readiness succeeds, and local port 9090 is
free. Then, in a dedicated terminal, start:

```bash
kubectl --context kind-kube-optimizer --namespace kri-monitoring \
  port-forward --address 127.0.0.1 service/kri-prometheus 9090:9090
```

Keep that foreground process visible. In another terminal verify the exact URL
used by the project:

```bash
curl --fail --silent --show-error http://127.0.0.1:9090/-/ready
curl --fail --silent --show-error --get \
  http://127.0.0.1:9090/api/v1/query \
  --data-urlencode 'query=up'
```

Require `Prometheus Server is Ready.` and `up == 1` for Prometheus, cAdvisor,
and both application Pods. Before an approved experiment, additionally require
usable samples—not merely target health—for every M14 metric family.

To roll back this access restoration, press Ctrl-C in the port-forward terminal
and confirm port 9090 is no longer listening. There is no Kubernetes cleanup
because this procedure creates no Kubernetes object.

## Approval-gated fallback only

Use the checked-in deployment asset only if a fresh read-only inspection later
shows a missing or drifted project-owned object. That is not the current state.
Any apply is a persistent Kubernetes mutation and needs separate explicit
approval bound to this context, manifest path, and digest:

```bash
kubectl --context kind-kube-optimizer apply \
  -f deploy/monitoring/prometheus.yaml
kubectl --context kind-kube-optimizer --namespace kri-monitoring \
  rollout status deployment/kri-prometheus --timeout=120s
```

After an approved apply, repeat the readiness, target, endpoint, and metric
checks before starting a load Job. Do not use `kubectl delete -f` as routine
rollback: it removes the namespace plus cluster and `payments` RBAC. Deletion
requires its own explicit approval and is appropriate only for intentional
monitoring teardown, not restoration failure.
