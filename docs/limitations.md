# Limitations and claim boundaries

The evidence supports hands-on single-node Kubernetes deployment, explicit NVIDIA GPU resource scheduling, containerised CUDA inference, startup/readiness handling, a controlled Docker/Kubernetes comparison, desired-state reconciliation and one real inference Pod deletion/recovery experiment.

- One physical node, one advertised V100, no HA, no multi-node scheduling, no distributed storage or node-failure recovery proof.
- Read-only node-local `hostPath` storage and a node selector deliberately bind the workload to that machine.
- No GPU sharing or time slicing; V100 has no MIG. The host's other NVIDIA GPU was excluded from the advertised resource.
- Native GPU workloads are invisible to Kubernetes GPU accounting. A separate ownership handoff is required; allocatable count is not free VRAM.
- Three short measured benchmark runs per configuration, one synthetic deterministic request, no soak test, no concurrency/streaming/TTFT study or statistical significance claim. Server throughput is distinct from client elapsed.
- MTP improvement is application optimisation on this model/prompt. Output identity establishes this controlled comparison, not universal output quality or speedup.
- One cached-image/model Pod recovery is not an SLA or proof of recovery from node, GPU, driver, storage or network failure. Timing precision is bounded by clocks, API timestamp resolution and observer delivery.
- No established permanent-hang failure mode or liveness restart policy. Health readiness is not comprehensive reliability qualification.
- No production uptime, production Kubernetes tenure, large-fleet operation, production SRE ownership, HA Kubernetes design, production GPU Operator expertise or production reliability qualification is claimed.
- GPU Operator was deliberately not required for the bounded core. GitOps, CI/CD, observability infrastructure, GPU sharing and multi-node inference remain future work.
- No production authentication/exposure/hardening assessment was performed. The benchmark endpoint was temporary loopback access; the stable Service was ClusterIP.
- The application archive and weights are absent. Source-pinned rebuilds can differ because upstream base images/packages and CPU-native build settings are not fully frozen by the source SHA. Reproduction on another machine is a new experiment.

Private retained evidence contains raw observations and aborted preparations. This public repository curates small exact result artifacts and source-derived documentation; it does not supply a complete independent raw-trace audit packet. Publication curation added no host/platform changes and reran no experiments.
