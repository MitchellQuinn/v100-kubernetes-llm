# Implementation notes and reproduction

## Bounded engineering decisions

- **K3s:** a compact distribution supplied a real Kubernetes control plane and node runtime for the single-node experiment without adding fleet infrastructure.
- **Separate containerd:** Docker/system containerd remained independent of K3s embedded containerd. The frozen image archive was imported into K3s rather than rebuilding it or redirecting Docker to the Kubernetes runtime.
- **Existing driver:** the working NVIDIA R580 host driver was preserved. Container Toolkit/runtime integration and the device plugin supplied the required runtime/scheduling interfaces.
- **GPU Operator:** deliberately unnecessary for this bounded core; installing the runtime and official device plugin proved the required resource scheduling without claiming Operator experience.
- **V100-only discovery:** the host also had a Quadro P1000. The plugin used RuntimeClass `nvidia` and `NVIDIA_VISIBLE_DEVICES` scoped to the V100 so one advertised resource represented the intended compute device.
- **Recreate:** one replica and one GPU make rolling-update surge inappropriate. Recreate expresses one-at-a-time update ownership, while deletion reconciliation can still create a pending replacement before termination finishes.
- **hostPath:** a read-only existing model directory was adequate on one fixed node. This deliberately trades portability for a small, inspectable experiment.
- **GPU ownership handoff:** the Kubernetes Deployment was scaled to zero before restoring native llama. Non-Kubernetes GPU memory use is invisible to Kubernetes resource accounting.
- **Probes:** startup accommodates legitimate model initialisation and readiness gates routing. No distinct permanent-hang failure mode had been established, so no liveness restart policy was invented.

During the earlier CPU-only K3s phase, its service PATH deliberately prevented NVIDIA runtime discovery. The GPU phase restored a normal service PATH, after which K3s detected the runtime and generated its NVIDIA handler. RuntimeClass objects already existed; their presence alone was not proof of runtime configuration. This history is documented, not reproduced by an automated host-setup script.

## Recorded provenance

| Object | Recorded identity |
| --- | --- |
| Fork | [anyei/llamacpp-v100 at d6c02899a83c175fc3e56f3b07c6da0f4b6e5ee3](https://github.com/anyei/llamacpp-v100/tree/d6c02899a83c175fc3e56f3b07c6da0f4b6e5ee3) |
| Docker reported image ID / OCI index | `sha256:c1f04ac7a250a962eaa1ed324f20571b3b57976df91c18955d02f30cb49bc3b0` |
| Linux/amd64 executable manifest | `sha256:32043481233e7a783caaa14d5ec346b239f91df96b5ffa043a02a4eccb82644b` |
| Image config / CRI image ID / Pod imageID | `sha256:1923ac31787f643f25d8944c67804d7dfac83ad7fa16db27a71c323426d91d09` |
| Private Docker archive SHA-256 | `912ba56efeccd9e8848ffee908ff5e1b67ca5a800c3bc383c9422a0cd5c524b5` |
| GGUF SHA-256 | `493301830a596b8ad56dc1329f80bbcb578c8e910da395feafdc9cd8263430bb` |

These are different digest objects, not interchangeable labels. The recorded Docker implementation reported the OCI index as its image ID. K3s used the imported executable content and image configuration. The local convenience tag `docker.io/library/llamacpp-v100:k8s-baseline` is not itself immutable; the archive/content verification established the frozen bytes in the actual experiment.

Build used the pinned fork's `.devops/cuda.Dockerfile`, server target and `CUDA_DOCKER_ARCH=70`, with CUDA 12.8.1 / Ubuntu 24.04 defaults. The Dockerfile includes moving base-image tags, package repositories and `GGML_NATIVE=ON`; pinning the fork is therefore insufficient for a bit-identical rebuild or arbitrary CPU portability. The private archive is neither included nor publicly downloadable from this repository.

The recorded GGUF filename, size and SHA-256 match the [Unsloth published LFS pointer](https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/raw/main/Qwen3.8-27B-UD-Q6_K_M.gguf), checked during curation. This establishes matching bytes, not the historical download route or revision, which was not retained. Acquire the weights separately under their upstream terms and verify the hash; do not substitute a similarly named quantisation silently.

## Reproduction procedure

This is an inspectable procedure for a separately prepared evaluation host. It was not executed during publication curation and is not an installer or fresh-host acceptance test.

1. Prepare Linux, a compatible NVIDIA driver and Container Toolkit/runtime, and K3s v1.37.1+k3s1. Ensure K3s can discover `nvidia-container-runtime` in its service PATH and actually configures its NVIDIA handler. Keep Docker/system containerd separate. Review the generic [K3s config](../manifests/k3s-config.yaml), which disables Traefik/ServiceLB and names the node `v100-node`.
2. Obtain the matching GGUF separately. Put it in `/srv/models/qwen-3.8`, or edit the public hostPath. That directory must already exist (`type: Directory`); the mount is read-only. Verify the recorded hash and stop conflicting native GPU workloads before allocating the GPU here.
3. Build the selected source or supply an explicitly identified compatible image. A source-pinned build example is below. Record the resulting identities and use that same frozen artifact for both runtime comparisons. A fresh build is not assumed to match the private archive digest.

```sh
git clone https://github.com/anyei/llamacpp-v100.git
cd llamacpp-v100
git checkout --detach d6c02899a83c175fc3e56f3b07c6da0f4b6e5ee3
docker build -f .devops/cuda.Dockerfile --target server \
  --build-arg CUDA_DOCKER_ARCH=70 \
  --build-arg APP_REVISION=d6c02899a83c175fc3e56f3b07c6da0f4b6e5ee3 \
  --build-arg APP_VERSION=11044 \
  --build-arg BUILD_DATE=2026-10-04T13:34:55.373882+00:00 \
  --build-arg IMAGE_SOURCE=https://github.com/anyei/llamacpp-v100/ \
  --build-arg IMAGE_URL=https://github.com/anyei/llamacpp-v100/ \
  -t llamacpp-v100:k8s-baseline .
docker image save -o ../llamacpp-v100.docker.tar llamacpp-v100:k8s-baseline
```

4. From this portfolio repository, use `scripts/import-image.sh /path/to/llamacpp-v100.docker.tar`. The helper imports into K3s containerd's `k8s.io` namespace. Verify the imported tag/content; the helper does not certify archive provenance.
5. Replace `<V100-GPU-UUID>` in [the device plugin manifest](../manifests/nvidia-device-plugin-v100.yaml) with the chosen V100 identifier obtained on the evaluation host. Apply the plugin and verify Node Capacity/Allocatable `nvidia.com/gpu: 1`. The plugin image is pinned to upstream version v0.20.1, matching the experiment's version-tag pattern; no digest pin for that upstream image is claimed.
6. Match the Deployment's generic node selector to your configured node name; retain one GPU, one replica, NVIDIA RuntimeClass, model/arguments and probes. Apply Namespace, Deployment and Service in that order.

```sh
sudo k3s kubectl apply -f manifests/nvidia-device-plugin-v100.yaml
sudo k3s kubectl apply -f manifests/inference/namespace.yaml
sudo k3s kubectl apply -f manifests/inference/deployment.yaml
sudo k3s kubectl apply -f manifests/inference/service.yaml
sudo k3s kubectl -n v100-inference rollout status deployment/llamacpp-v100
sudo k3s kubectl -n v100-inference port-forward \
  --address 127.0.0.1 service/llamacpp-v100 8097:8080
```

7. In another terminal, use the [benchmark procedure](benchmark-methodology.md). Docker should use the same image, model mount and Deployment argument array, NVIDIA runtime, selected GPU, and loopback mapping `127.0.0.1:8097:8080`; run the two configurations sequentially with ownership handoff. Compare response settings, output bytes and MTP counts as well as metrics.
8. Terminate the temporary port-forward and scale the Deployment to zero before restoring a native GPU service. Verify GPU release independently; a Kubernetes resource count cannot prove the GPU is free of native processes.

Public placeholders change only lab-specific values, not scheduling/storage semantics. Authentication, external exposure, production hardening and ownership coordination are operator responsibilities outside this bounded reproduction recipe.
