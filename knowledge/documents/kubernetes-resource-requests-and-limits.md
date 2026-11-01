# Kubernetes Resource Requests and Limits

## Scope

This reference distinguishes scheduling requests from runtime limits for
container CPU and memory. It applies to the per-container resources collected by
this project.

## Canonical behavior

- The scheduler uses resource requests when deciding whether a Pod fits on a
  node. Actual usage above a request does not by itself violate a runtime limit.
- A CPU request influences scheduling and CPU weighting under contention. It is
  not a hard ceiling.
- A CPU limit is enforced through cgroup CPU quota and can cause throttling when
  runnable work demands more CPU time than the quota permits.
- A memory request primarily affects scheduling. It does not reserve a private
  block of memory equal to the request.
- A memory limit is enforced reactively. Exceeding it can lead to an OOM kill;
  it is not equivalent to CPU throttling.
- CPU quantities use cores or millicpu (`100m` equals `0.1` CPU). Binary memory
  quantities such as `Mi` and `Gi` are distinct from decimal units.

## Diagnostic interpretation

Compare usage with the matching resource at the same container scope. A request
mismatch means scheduling intent does not represent observed demand; it does not
prove runtime throttling or memory pressure. A limit-pressure finding requires
limit-relative evidence such as CPU throttling, CPU usage near quota, memory
working set near the limit, OOM events, or restarts.

## Safety boundary

Resource changes require approval and a post-change observation. Do not infer a
safe decrease from missing or short-window data.
