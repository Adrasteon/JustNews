#!/usr/bin/env python3
"""Simulate concurrent agent inference requests against a single base model + adapters.

This script has two modes:
 - test mode (RE_RANKER_TEST_MODE=1) which uses a fast deterministic stub model to
   exercise the concurrency, GPU usage measurement and latency pipeline without
   loading heavy models.
 - real mode: if the environment has transformers + bitsandbytes, will attempt to
   load `RE_RANKER_MODEL` or a given model id and run real inference.

Usage examples
  # Dry-run with stub (fast, no heavy downloads)
  RE_RANKER_TEST_MODE=1 python scripts/perf/simulate_concurrent_inference.py --workers 8 --requests 100

  # Try real model load (must have CUDA + bnb and model available)
  RE_RANKER_TEST_MODE=0 RE_RANKER_MODEL=mistralai/Mistral-7B-Instruct python scripts/perf/simulate_concurrent_inference.py --workers 3 --requests 30

The script reports per-request latency (p50, p95, max) and GPU memory snapshots.
"""

from __future__ import annotations

import argparse
import os
import time
import statistics
import concurrent.futures
from typing import Tuple, List

try:
    import pynvml
    NVML_AVAILABLE = True
except Exception:
    NVML_AVAILABLE = False

RETRY_SLEEP = 0.01


def gpu_mem_snapshot() -> Tuple[int, int]:
    if not NVML_AVAILABLE:
        return (0, 0)
    try:
        pynvml.nvmlInit()
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        m = pynvml.nvmlDeviceGetMemoryInfo(h)
        return (int(m.total // 1024**2), int(m.used // 1024**2))
    except Exception:
        return (0, 0)


class StubModel:
    def score(self, query: str, text: str) -> float:
        # cheap deterministic work to simulate compute
        s = sum(ord(c) for c in query) % (len(text) + 1)
        # simulate some GPU-like delay (tiny)
        time.sleep(0.002)
        return float(s) / (len(text) + 1)


def load_model_if_available(model_id: str | None):
    if os.environ.get('RE_RANKER_TEST_MODE', '1') in ('1', 'true'):
        return StubModel()

    try:
        # Try real loading
        from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
        import torch
        model_id = model_id or os.environ.get('RE_RANKER_MODEL')
        if not model_id:
            raise RuntimeError('No model id configured (RE_RANKER_MODEL)')

        bnb = BitsAndBytesConfig(load_in_8bit=True, bnb_8bit_use_double_quant=True, bnb_8bit_compute_dtype=getattr(torch, 'float16', None))
        model = AutoModelForCausalLM.from_pretrained(model_id, quantization_config=bnb, device_map='auto')
        tokenizer = AutoTokenizer.from_pretrained(model_id)

        class RealScorer:
            def __init__(self, m, tkn):
                self.m = m
                self.t = tkn

            def score(self, q, c):
                inp = f"Query: {q}\nCandidate: {c}\nScore:"
                tokens = self.t(inp, return_tensors='pt')
                if torch.cuda.is_available():
                    tokens = {k: v.to('cuda') for k, v in tokens.items()}
                with torch.no_grad():
                    out = self.m(**tokens)
                # heuristic: return max softmax on last token
                logits = out.logits[:, -1, :]
                probs = logits.softmax(dim=-1).max().values.item()
                return float(probs)

        return RealScorer(model, tokenizer)
    except Exception as e:
        print('Warning: failed to load real model - falling back to stub:', e)
        return StubModel()


def worker_task(worker_id: int, scorer, num_requests: int) -> List[float]:
    latencies = []
    for i in range(num_requests):
        q = f"Test query from worker {worker_id} iter {i}"
        cand = "The company reported record revenue this quarter with strong growth"
        t0 = time.monotonic()
        _ = scorer.score(q, cand)
        lat = (time.monotonic() - t0) * 1000.0
        latencies.append(lat)
    return latencies


def run_workers(workers: int, total_requests: int, model_id: str | None = None):
    requests_per_worker = max(1, total_requests // workers)
    print(f"Running {workers} workers, total requests {total_requests} (~{requests_per_worker} each)")
    scorer = load_model_if_available(model_id)

    # warmup snapshot
    total_mb, used_mb = gpu_mem_snapshot()
    print(f"GPU snapshot before workers: total={total_mb}MB used={used_mb}MB")

    start = time.monotonic()
    all_latencies: List[float] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(worker_task, i, scorer, requests_per_worker) for i in range(workers)]
        for fut in concurrent.futures.as_completed(futures):
            all_latencies.extend(fut.result())

    duration = time.monotonic() - start

    total_mb2, used_mb2 = gpu_mem_snapshot()
    print(f"GPU snapshot after: total={total_mb2}MB used={used_mb2}MB")

    print(f"Total completed requests: {len(all_latencies)} in {duration:.2f}s")
    if all_latencies:
        print(f"p50={statistics.median(all_latencies):.1f}ms p95={statistics.quantiles(all_latencies, n=100)[94]:.1f}ms max={max(all_latencies):.1f}ms avg={statistics.mean(all_latencies):.1f}ms")
    return {
        'total_requests': len(all_latencies),
        'duration_s': duration,
        'gpu_used_before_mb': used_mb,
        'gpu_used_after_mb': used_mb2,
    }


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--workers', type=int, default=4)
    p.add_argument('--requests', type=int, default=100)
    p.add_argument('--model', type=str, default=None)
    args = p.parse_args(argv)

    res = run_workers(args.workers, args.requests, args.model)
    print('\nSummary:')
    for k, v in res.items():
        print(f"  {k}: {v}")


if __name__ == '__main__':
    main()
