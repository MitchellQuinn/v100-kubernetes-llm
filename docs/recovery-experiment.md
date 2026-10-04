# Real inference Pod deletion and recovery

The retained Phase 8 report records exactly one ordinary inference Pod deletion on 2026-10-04. The Deployment desired one replica throughout the successful experiment. Deployment, ReplicaSet and ClusterIP Service retained their identities; the replacement had a different Pod name, UID, address and container identity. Personal node/device/network identifiers are omitted from this public account.

Kubernetes did not restart the deleted Pod. The Deployment's desired state caused its ReplicaSet to create a new Pod with a new identity. An ordinary `delete pod ... --wait=false` preserved normal termination grace; no force deletion, template update, platform tuning or throughput rerun occurred.

## Timeline

Zero is the client deletion-request timestamp, before command process launch, rather than exact API-server receipt. Rows use distinct retained timing sources; first watch observations are detection upper bounds.

| Milestone | Seconds from deletion | Measurement source |
| --- | ---: | --- |
| Original termination begins, observed | 0.229158 | Pod watch receipt |
| Replacement created, observed | 0.233964 | Pod ADDED watch receipt |
| Original container terminated, observed | 0.756140 | Pod watch receipt |
| Replacement scheduler assignment | 0.758231 | Scheduler event timestamp; watch receipt 0.758739 |
| Original Pod removed, observed | 1.398043 | Pod DELETED watch receipt |
| Replacement container start | 1.568721 | CRI startedAt |
| Replacement container Running, observed | 1.581004 | Pod watch receipt |
| Replacement endpoint unready, observed | 1.584500 | EndpointSlice watch receipt |
| Model loaded | 6.699157 | CRI application log timestamp |
| Container started=true, observed | 7.093456 | Pod watch receipt after startup probe |
| Pod Ready, observed | 7.099984 | Pod watch receipt |
| EndpointSlice ready, observed | 7.104477 | EndpointSlice watch receipt |
| First Service HTTP 200 response | 7.192963 | Actual ClusterIP client response completion |
| First successful small inference response | 7.513479 | Actual ClusterIP client response completion |

## Sole-GPU allocation

Replacement creation overlapped original termination. The replacement briefly received `FailedScheduling: Insufficient nvidia.com/gpu`. It could not receive the sole advertised GPU until the original allocation was released. The scheduler subsequently placed it without a second GPU. The original container completed normally with exit code 0; the replacement had zero restarts.

`Recreate` controls Deployment updates; it does not prevent this deletion-driven overlap of a terminating original and pending replacement. The other NVIDIA GPU on the host was deliberately excluded from device-plugin discovery. The replacement obtained the same V100 and retained one-GPU requests/limits, NVIDIA RuntimeClass, model, image and arguments.

## Running, model loaded, Ready and usable

Application loading-to-loaded elapsed span was 4.924732 seconds, including context/MTP initialisation and warm-up. Container start to loaded log was 5.130436 seconds. Logs confirmed CUDA, 66/66 offloaded layers, flash attention and native MTP n=2.

There were 33 sampled observations with container Running but Pod NotReady and no ready Service endpoint; ClusterIP health failed in those samples. Direct replacement `/health` returned 503 in 28 startup samples. These are expected initialisation observations. The startup probe gates readiness; its exact success instant is not independently exposed. `started=true` is subsequent status evidence.

EndpointSlice initially advertised the replacement as ready=false, then ready=true after Pod readiness was observed. `publishNotReadyAddresses` was not enabled. The Service identity/address persisted while its usable endpoint changed. An actual ClusterIP `/health` response completed with HTTP 200 at +7.192963 seconds. A subsequent `Say hello.` request with n_predict=8, temperature=0 and seed=1234 succeeded at +7.513479 seconds, generating eight tokens. This functional proof is not a throughput benchmark.

**Container running != Pod Ready != Service usable.** Recovery was demonstrated by a real Service response and inference, not merely by a started process.

## Preparation, cleanup and timing boundaries

Two observer preparations were aborted before any deletion; one stopped before scale-up and one after readiness because Event-watch URL validation failed. Both restored the native service. Corrected watches were verified before the one successful deletion. Post-run parsing corrections affected derived observations only. Failed preparations remain in the private evidence; the public result does not imply three independent recovery trials.

After observations were retained, the Deployment was scaled to zero and the native non-Kubernetes model service restored. Kubernetes GPU accounting cannot see that native workload, so this handoff was necessary. The saved declarative manifest continues to specify one replica; it is not a statement that the experiment remains running.

Watch/HTTP clients used the same host monotonic clock. Runtime/log timestamps used wall time, normalised from retained time zones. Kubernetes creation/Ready timestamp fields have second resolution; arithmetic on those fields must not outrank finer log/watch evidence. CRI precision and microsecond reporting do not prove microsecond accuracy. Watch delivery and polling add latency; independent streams do not establish strict hidden controller ordering. No independent startup-probe-success timestamp is claimed.

This is one cached-image/model recovery on one physical node. It does not establish an SLA, HA, recovery from node/driver/GPU failure, forced termination behaviour or production reliability qualification.
