#!/usr/bin/env python3
"""Sanitised public benchmark helper, not the source of published CSVs.

Published CSVs are retained experiment results, not regenerated during publication.
This helper performs one nonstreaming inference request and captures lightweight
GPU/host samples. Linux /proc and nvidia-smi are required; no third-party Python
packages are needed.
"""

import argparse
import csv
import datetime as dt
import hashlib
import http.client
import json
import math
import pathlib
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from contextlib import ExitStack

BENCHMARK_DIRECTORY = pathlib.Path(__file__).resolve().parent
REQUEST_TIMEOUT_SECONDS = 240
SAMPLE_INTERVAL_SECONDS = 0.5
GPU_HEADER = [
    "timestamp_utc", "index", "name", "memory_used_mib",
    "gpu_util_percent", "power_w", "temperature_c",
]
HOST_HEADER = [
    "timestamp_utc", "cpu_busy_percent", "mem_total_kib",
    "mem_available_kib", "swap_used_kib",
]


class BenchmarkError(Exception):
    """A request or response failed benchmark validation."""


def gpu_selector(value):
    if not re.fullmatch(r"[0-9]+|GPU-[A-Za-z0-9-]+", value):
        raise argparse.ArgumentTypeError("expected a GPU index or GPU-... UUID")
    return value


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run", required=True, choices=["warmup", "run-01", "run-02", "run-03"],
    )
    parser.add_argument("--endpoint", default="http://127.0.0.1:8097/completion")
    parser.add_argument(
        "--request", type=pathlib.Path, default=BENCHMARK_DIRECTORY / "request.json",
    )
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    parser.add_argument(
        "--gpu", type=gpu_selector, required=True,
        help="GPU index or GPU-... UUID passed to nvidia-smi -i",
    )
    return parser.parse_args()


def load_request_bytes(path):
    # Submit the exact file bytes; do not parse/reserialise the request.
    return path.read_bytes()


def validate_output_directory(path):
    directory = path.resolve()
    if directory == BENCHMARK_DIRECTORY or BENCHMARK_DIRECTORY in directory.parents:
        raise BenchmarkError("use an output directory outside repository benchmarks/")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def build_output_paths(directory, run_name):
    suffixes = {
        "response": ".response.json", "client": ".client.json",
        "gpu": ".gpu.csv", "host": ".host.csv",
    }
    paths = {
        key: directory / (run_name + suffix) for key, suffix in suffixes.items()
    }
    for path in paths.values():
        if path.exists() or path.is_symlink():
            raise BenchmarkError(f"refusing existing file: {path}")
    return paths


def query_gpu_samples(selector):
    completed = subprocess.run(
        [
            "nvidia-smi", "-i", selector,
            "--query-gpu=index,name,memory.used,utilization.gpu,power.draw,temperature.gpu",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True, text=True, timeout=15,
    )
    if completed.returncode != 0:
        raise ValueError(f"nvidia-smi exited with status {completed.returncode}")
    samples = []
    errors = []
    for row_number, row in enumerate(csv.reader(completed.stdout.splitlines()), 1):
        values = [value.strip() for value in row]
        try:
            if len(values) != 6 or not values[0].isdigit() or not values[1]:
                raise ValueError("expected index, name and four numeric measurements")
            numbers = [float(value) for value in values[2:]]
            if any(not math.isfinite(value) or value < 0 for value in numbers):
                raise ValueError("expected finite, non-negative measurements")
            samples.append(values)
        except ValueError as error:
            errors.append(f"nvidia-smi row {row_number}: {error}")
    if not samples and not errors:
        errors.append("nvidia-smi returned no GPU rows")
    return samples, errors


def read_host_sample(previous_cpu):
    fields = pathlib.Path("/proc/stat").read_text().splitlines()[0].split()
    if len(fields) < 9 or fields[0] != "cpu":
        raise ValueError("/proc/stat: expected aggregate CPU counters")
    counters = [int(value) for value in fields[1:9]]
    if any(value < 0 for value in counters):
        raise ValueError("/proc/stat: negative CPU counter")
    total = sum(counters)
    idle = counters[3] + counters[4]
    busy_percent = None
    if previous_cpu is not None:
        total_delta = total - previous_cpu[0]
        idle_delta = idle - previous_cpu[1]
        if total_delta < 0 or idle_delta < 0 or idle_delta > total_delta:
            raise ValueError("/proc/stat: inconsistent CPU counter deltas")
        if total_delta:
            busy_percent = 100 * (1 - idle_delta / total_delta)
    required = {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}
    memory = {}
    for line in pathlib.Path("/proc/meminfo").read_text().splitlines():
        key, separator, value = line.partition(":")
        if key in required:
            parts = value.split()
            if not separator or len(parts) != 2 or parts[1] != "kB":
                raise ValueError(f"/proc/meminfo: malformed {key}")
            memory[key] = int(parts[0])
    if required - memory.keys():
        raise ValueError("/proc/meminfo: missing required memory counters")
    if (
        any(value < 0 for value in memory.values())
        or memory["MemAvailable"] > memory["MemTotal"]
        or memory["SwapFree"] > memory["SwapTotal"]
    ):
        raise ValueError("/proc/meminfo: inconsistent memory counters")
    return [
        busy_percent, memory["MemTotal"], memory["MemAvailable"],
        memory["SwapTotal"] - memory["SwapFree"],
    ], (total, idle)


def resource_sampler(stop, selector, gpu_samples, host_samples, warnings):
    previous_cpu = None
    while not stop.is_set():
        stamp = dt.datetime.now(dt.timezone.utc).isoformat()
        # Each source fails independently. Queue messages across the thread boundary.
        try:
            rows, errors = query_gpu_samples(selector)
            gpu_samples.extend([stamp] + row for row in rows)
            for error in errors:
                warnings.put(f"{stamp} GPU: {error}")
        except Exception as error:
            warnings.put(f"{stamp} GPU: {type(error).__name__}: {error}")
        try:
            row, previous_cpu = read_host_sample(previous_cpu)
            host_samples.append([stamp] + row)
        except Exception as error:
            previous_cpu = None
            warnings.put(f"{stamp} host: {type(error).__name__}: {error}")
        stop.wait(SAMPLE_INTERVAL_SECONDS)


def execute_request(endpoint, body):
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    start_counter = time.perf_counter()
    status = None
    raw = b""
    client_error = None
    try:
        request = urllib.request.Request(
            endpoint, data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            response = urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            status = response.code
            try:
                raw = response.read()
            except http.client.IncompleteRead as error:
                raw = error.partial
                raise
    except Exception as error:
        client_error = f"{type(error).__name__}: {error}"
    elapsed = time.perf_counter() - start_counter
    return status, raw, client_error, started, elapsed


def write_csv(output, header, rows):
    writer = csv.writer(output)
    writer.writerow(header)
    writer.writerows(rows)


def write_client_metadata(output, metadata):
    json.dump(metadata, output, indent=2)
    output.write("\n")


def parse_response_json(raw):
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as error:
        raise BenchmarkError(f"expected JSON response; observed invalid JSON: {error}") from error
    if not isinstance(result, dict):
        raise BenchmarkError(f"expected JSON object; observed {type(result).__name__}")
    return result


def validate_response(status, result):
    if status != 200:
        raise BenchmarkError(f"expected HTTP 200; observed {status!r}")
    content = result.get("content")
    if not isinstance(content, str) or not content:
        raise BenchmarkError(f"expected non-empty generated content; observed {content!r}")
    timings = result.get("timings")
    if not isinstance(timings, dict):
        raise BenchmarkError(f"expected timings object; observed {timings!r}")
    rate = timings.get("predicted_per_second")
    if (
        isinstance(rate, bool) or not isinstance(rate, (int, float))
        or not math.isfinite(rate) or rate <= 0
    ):
        raise BenchmarkError(f"expected positive predicted_per_second; observed {rate!r}")
    tokens = result.get("tokens_predicted")
    if tokens != 256:
        raise BenchmarkError(f"expected exactly 256 predicted tokens; observed {tokens!r}")
    cache_count = timings.get("cache_n")
    if isinstance(cache_count, bool) or cache_count != 0:
        raise BenchmarkError(f"expected cache_n == 0; observed {cache_count!r}")


def print_summary(run_name, status, elapsed, result):
    print(json.dumps({
        "run": run_name, "status": status, "client_elapsed_s": elapsed,
        "content_preview": result.get("content", "")[:100],
        "tokens_predicted": result.get("tokens_predicted"),
        "timings": result.get("timings"),
    }), flush=True)


def main():
    args = parse_args()
    body = load_request_bytes(args.request)
    directory = validate_output_directory(args.output_dir)
    paths = build_output_paths(directory, args.run)
    gpu_samples = []
    host_samples = []
    warnings = queue.Queue()
    stop = threading.Event()
    sampler = threading.Thread(
        target=resource_sampler,
        args=(stop, args.gpu, gpu_samples, host_samples, warnings),
    )
    # Exclusive creation also prevents overwriting files created after the precheck.
    with ExitStack() as stack:
        outputs = {}
        for key, path in paths.items():
            if key == "response":
                outputs[key] = stack.enter_context(path.open("xb"))
            else:
                outputs[key] = stack.enter_context(
                    path.open("x", encoding="utf-8", newline=""),
                )
        sampler.start()
        try:
            status, raw, client_error, started, elapsed = execute_request(args.endpoint, body)
        finally:
            stop.set()
            sampler.join()
        sampler_warnings = []
        while not warnings.empty():
            sampler_warnings.append(warnings.get_nowait())
        for warning in sampler_warnings:
            print(f"sampler warning: {warning}", file=sys.stderr)
        outputs["response"].write(raw)
        write_csv(outputs["gpu"], GPU_HEADER, gpu_samples)
        write_csv(outputs["host"], HOST_HEADER, host_samples)
        metadata = {
            "run": args.run, "started_utc": started, "elapsed_seconds": elapsed,
            "http_status": status, "request_sha256": hashlib.sha256(body).hexdigest(),
            "endpoint": args.endpoint, "stream": False, "ttft_seconds": None,
            "ttft_reason": "not measurable by this nonstreaming client",
            "gpu_samples": len(gpu_samples), "host_samples": len(host_samples),
            "selected_gpu": args.gpu, "sampler_warning_count": len(sampler_warnings),
            "sampler_warnings": sampler_warnings,
        }
        if client_error:
            metadata["client_error"] = client_error
        write_client_metadata(outputs["client"], metadata)
    # Close all evidence files before reporting request/validation failures.
    if client_error:
        raise BenchmarkError(f"request failed: {client_error}; evidence saved in {directory}")
    if status != 200:
        raise BenchmarkError(f"expected HTTP 200; observed {status!r}; raw response saved")
    result = parse_response_json(raw)
    validate_response(status, result)
    print_summary(args.run, status, elapsed, result)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (BenchmarkError, OSError) as error:
        print(f"benchmark error: {error}", file=sys.stderr)
        sys.exit(1)
