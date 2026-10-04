# Controlled benchmark methodology

The dated Docker/MTP and K3s phase reports and their retained request/response/result files are the authority. Public CSVs are exact small copies, including the excluded warm-up row; no benchmarks were rerun during publication curation.

## Frozen inputs

- Fork SHA: `d6c02899a83c175fc3e56f3b07c6da0f4b6e5ee3`.
- The exact frozen Docker archive was imported into K3s, with no application rebuild or registry pull. Digest identities are documented in [implementation notes](implementation-notes.md#recorded-provenance).
- Model: `Qwen3.8-27B-UD-Q6_K_M.gguf`, 23,088,409,504 bytes, SHA-256 `493301830a596b8ad56dc1329f80bbcb578c8e910da395feafdc9cd8263430bb`.
- Exact [request](../benchmarks/request.json) SHA-256: `358aca25b36ebb0a600fed4bc492ca064d4f6cd1dc5a810050e8376ba5f5a707`.

Server settings: `/app/llama-server --model /models/Qwen3.8-27B-UD-Q6_K_M.gguf --device CUDA0 --n-gpu-layers 99 --ctx-size 8192 --parallel 1 --flash-attn on --cache-type-k f16 --cache-type-v f16 --fit off --spec-type draft-mtp --spec-draft-n-max 2 --host 0.0.0.0 --port 8080 --log-verbosity 4`. Effective inference/batch thread defaults were 6/6, batch 2048, microbatch 512. Logs confirmed CUDA, 66/66 offloaded layers, flash attention and native MTP n=2. No separate draft model was used.

The target-only Docker comparison changed only speculation: `--spec-type none`, without `--spec-draft-n-max 2`. It used the same image/model/request and other server settings. Earlier target-only runs were neither interleaved with nor rerun during the MTP addendum. The pre-existing native Vulkan service had different settings and unresolved build provenance; it is contextual evidence, excluded from these controlled comparisons.

## Request, repetitions and metrics

The nonstreaming sequence-continuation request uses n_predict=256, temperature=0, seed=1234, top_k=1, top_p=1, min_p=0, repeat_penalty=1 and cache_prompt=false. Every warm-up/measured request processed 557 prompt tokens, generated 256 tokens and reported cache_n=0. One warm-up preceded three sequential measured runs; no measured request was discarded.

Server prefill/decode are llama.cpp response `timings.prompt_per_second` and `timings.predicted_per_second`. Client elapsed uses `time.perf_counter()` around HTTP request/response completion. These are different metrics. Docker used a loopback published port; Kubernetes used the same loopback destination through temporary Service port-forwarding. Kubernetes client elapsed therefore includes that forwarding path. Nonstreaming TTFT was not measured. Recovery Service-health observations used actual ClusterIP routing, separately from this benchmark transport.

The following values are rounded only for display. [Docker MTP CSV](../benchmarks/results/docker-mtp-n2.csv), [K3s MTP CSV](../benchmarks/results/k3s-mtp-n2.csv) and [target-only CSV](../benchmarks/results/docker-target-only.csv) retain the source precision and resource summaries.

| Runtime | Run | Prefill tokens/sec | Decode tokens/sec | Client elapsed s |
| --- | --- | ---: | ---: | ---: |
| Docker MTP n=2 | warmup (excluded) | 592.024149 | 57.891872 | 5.578182 |
| Docker MTP n=2 | run-01 | 583.185617 | 58.207694 | 5.379020 |
| Docker MTP n=2 | run-02 | 647.767818 | 58.262101 | 5.281152 |
| Docker MTP n=2 | run-03 | 646.896638 | 58.261371 | 5.281609 |
| K3s MTP n=2 | warmup (excluded) | 591.431359 | 57.824293 | 5.581329 |
| K3s MTP n=2 | run-01 | 601.698367 | 58.257089 | 5.347328 |
| K3s MTP n=2 | run-02 | 648.242762 | 58.297114 | 5.275240 |
| K3s MTP n=2 | run-03 | 648.513716 | 58.250713 | 5.285783 |

| Configuration | Mean prefill tokens/sec | Mean decode tokens/sec | Mean client elapsed s |
| --- | ---: | ---: | ---: |
| Docker target-only | 686.901 | 26.852 | 10.373 |
| Docker MTP n=2 | 625.950 | 58.244 | 5.314 |
| K3s MTP n=2 | 632.818 | 58.268 | 5.303 |

For fidelity to the K3s phase report, signed decode difference uses its rounded Docker baseline: `(58.268305283832 - 58.244) / 58.244 * 100 = +0.041730%`. The actual unrounded Docker mean is 58.24372209741943. Using both unrounded means would give a slightly different percentage; the published +0.0417% deliberately retains the report convention. MTP improvement uses unrounded Docker means and is +116.91% (displayed +116.9%). MTP prefill decreased 8.87% versus target-only; decode improvement does not mean every phase improved.

## Correctness and actual MTP engagement

Generated-text UTF-8 bytes were identical between target-only and Docker MTP, and between Docker MTP and corresponding K3s requests, including warm-up. Content SHA-256: `51d883709f74d845fa1e58cbf2f8a5a2372decc2c8a5856db567a002fbe8aa1b`. This refers to generated text, not timing-containing JSON response envelopes.

Every MTP request reported 174 drafted / 168 accepted tokens: 96.551724% acceptance. Measured totals were 522 / 504, excluding warm-up. Startup logs plus actual nonzero draft/accept counts establish engagement. The fork's `/props` default-generation speculative field alone was not treated as authoritative global runtime state. Output identity on this deterministic prompt does not establish general model quality.

## Resource sampling and limits

Retained samplers used `nvidia-smi` and `/proc` approximately every 0.5 seconds during each benchmark request. GPU VRAM, utilisation, power and temperature were sampled; CPU busy, MemAvailable and swap were broad host metrics, not Pod-specific accounting. Timed HTTP intervals were separate from before/after diagnostics. Small CSVs retain measured summaries; hundreds of raw samples, process snapshots and logs remain private.

K3s measured V100 VRAM ranged from 23,136 to 23,250 MiB; sampled maximum power was 218.56 W and temperature 54 C; swap remained zero. Docker MTP peaked at 23,250 MiB versus target-only 22,518 MiB. These are sampled observations, not continuous peak, energy or soak measurements. No relevant CUDA/OOM/inference failure was observed in the successful retained runs.

One node/GPU, three short runs per configuration, a synthetic prompt and sequential non-interleaved comparisons cannot establish universal overhead, significance, production latency, concurrent serving or long-duration stability. No CPU/memory resource limits were introduced for the comparison; ordinary runtime scheduling/cgroup differences were recorded rather than tuned away.

## Public runner

[run.py](../benchmarks/run.py) is a sanitised adaptation of the retained client. It keeps request bytes, HTTP timing, sampling interval and benchmark assertions, and accepts endpoint/request/output paths. It removes host-specific process/Docker snapshots and smoke-only support; it is not byte-identical to the private runner. It writes raw response/client/GPU/host records to a new evaluation directory, never the published result CSVs. Aggregate CSVs here are retained measurements, not newly generated results from the public runner.

For a separately prepared, ready server at the local endpoint:

```sh
python3 benchmarks/run.py --run warmup --output-dir evaluation-output
python3 benchmarks/run.py --run run-01 --output-dir evaluation-output
python3 benchmarks/run.py --run run-02 --output-dir evaluation-output
python3 benchmarks/run.py --run run-03 --output-dir evaluation-output
```

Use a different output directory for each runtime/configuration. Review raw responses and generated text as well as timing; preserve failed requests. The client requires Python standard library, Linux `/proc` and installed `nvidia-smi`, with no third-party Python packages. This publication task did not execute these commands.
