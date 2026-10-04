# Architecture and responsibilities

This is a single-node K3s server hosting a real CUDA llama.cpp workload. Control objects express desired state; node/runtime components provide execution; health and routing determine usability.

| Component | Responsibility in this experiment |
| --- | --- |
| K3s control plane | Hosts Kubernetes API, controller and scheduler functions and reconciles stored desired state. |
| Deployment / ReplicaSet | Deployment defines the Pod template and one desired replica; ReplicaSet reconciles that replica count. Pod deletion retains these owners and causes a replacement. |
| Scheduler | Selects the node using node constraints and the requested `nvidia.com/gpu` count. It does not load the model or measure free VRAM. |
| Kubelet | Executes the assigned Pod via CRI, manages device allocations through the registered plugin, runs probes and publishes status. |
| K3s embedded containerd | Stores imported application content and creates Pod sandboxes/containers through the configured runtime handler. |
| RuntimeClass `nvidia` | Selects K3s's NVIDIA runtime handler for opted-in Pods. A RuntimeClass declaration alone does not install that handler. |
| NVIDIA container runtime | Supplies the allocated GPU devices, driver libraries and runtime integration required for CUDA. |
| NVIDIA device plugin | Discovers the selected V100, registers it with kubelet and participates in allocation. Registration yields Capacity/Allocatable `nvidia.com/gpu: 1`. |
| llama.cpp Pod | Runs `/app/llama-server`, loads the frozen model and executes CUDA/native-MTP inference. Requests and limits one GPU. |
| ClusterIP Service / EndpointSlice | Service gives a stable destination. EndpointSlice tracks changing Pod addresses and readiness; only ready endpoints are eligible for normal routing. |
| Read-only `hostPath` | Makes an existing node-local model directory available at `/models`. No model transfer or portable storage claim is made. |

## Two container runtime domains

Docker uses the host's system containerd (observed 2.3.6). K3s uses its separate embedded containerd (2.3.4-k3s1). Their content stores, sockets, runtime configuration and workloads are separate. Installing an image in Docker does not make it available to kubelet. The experiment preserved Docker/system-containerd configuration and imported the frozen Docker archive directly into the K3s `k8s.io` namespace.

Direct archive import avoided a registry transfer or rebuild between the two measurements. Provenance verification matched the archive's executable manifest, image configuration and application layer content with K3s containerd. Non-executable build attestations are separate content objects; one unknown-platform attestation config was not retained by platform-selective import. No application content was rebuilt or substituted. `imagePullPolicy: Never` enforces local availability; the application is not obtained from a public registry.

## Control, GPU ownership and readiness

The generic node selector in the public manifest retains the experiment's node-bound semantics. `Recreate` avoids rolling-update overlap for a one-GPU deployment; it does not prohibit a ReplicaSet from creating a replacement while a deleted Pod is terminating. The scheduler can create a pending replacement but must wait for the previous GPU allocation to be released.

The NVIDIA handler is opt-in. Ordinary Pods retained the default runtime and no GPU request. The V100-only plugin configuration leaves the other NVIDIA GPU outside this advertised resource. Native GPU programs also sit outside Kubernetes accounting, so a separate operational ownership handoff was necessary.

The startup probe permits up to approximately 600 seconds of initialisation (2-second period, threshold 300). Readiness probes the same `/health` endpoint after startup succeeds. The Service did not route to the initialising Pod. Readiness neither guarantees every possible inference succeeds nor supplies a liveness restart policy. This bounded setup has no Ingress, NodePort, LoadBalancer, HA or distributed storage.
