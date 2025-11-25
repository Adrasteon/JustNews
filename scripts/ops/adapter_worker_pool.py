#!/usr/bin/env python3
"""Spawn a warm pool of adapter workers that load the shared base model + adapter.

This is an operational helper used for load testing and for establishing a warm
pool on a single GPU node. The script will spawn N worker processes which load
the base model (int8) then optionally a specified adapter and keep the process
alive ready to accept requests.

Note: in production, GPU Orchestrator should manage worker pools; this script
provides a developer-runable tool to prototype pool sizing and memory usage.
"""

from __future__ import annotations

import argparse
import importlib.util
import multiprocessing as mp
import os
import time


def worker_main(model_id: str | None, adapter: str | None, run_seconds: int = 3600):
    # workable minimal loader: use RE_RANKER_TEST_MODE for stub
    if os.environ.get('RE_RANKER_TEST_MODE', '1') in ('1', 'true'):
        print(f"[worker {os.getpid()}] running stub (test mode) — sleeping {run_seconds}s")
        time.sleep(run_seconds)
        return

    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        try:
            from transformers import BitsAndBytesConfig  # type: ignore
        except Exception:  # pragma: no cover - optional dependency
            BitsAndBytesConfig = None  # type: ignore

        load_kwargs: dict = {}
        bnb_cfg = None
        if BitsAndBytesConfig is not None:
            try:
                spec = importlib.util.find_spec('bitsandbytes')
                bnb_dir = None
                if spec and spec.submodule_search_locations:
                    bnb_dir = list(spec.submodule_search_locations)[0]
                has_native = bool(bnb_dir and os.path.isdir(bnb_dir) and any(name.startswith('libbitsandbytes') for name in os.listdir(bnb_dir)))
                if has_native:
                    bnb_cfg = BitsAndBytesConfig(load_in_8bit=True, bnb_8bit_use_double_quant=True, bnb_8bit_compute_dtype=getattr(torch, 'float16', None))
                    load_kwargs['quantization_config'] = bnb_cfg
                else:
                    print('[worker] bitsandbytes native binary missing — using float16 fp16 device_map')
            except Exception as e:
                print(f"[worker] bitsandbytes detection failed ({e}); using float16 fp16 device_map")
        else:
            print('[worker] transformers BitsAndBytesConfig unavailable — using float16 fp16 device_map')

        dtype = getattr(torch, 'float16', None)
        if bnb_cfg is None:
            model = AutoModelForCausalLM.from_pretrained(model_id, device_map='auto', dtype=dtype)
        else:
            model = AutoModelForCausalLM.from_pretrained(model_id, device_map='auto', **load_kwargs)

        # tokenizer not used directly here; call to warm model cache
        _ = AutoTokenizer.from_pretrained(model_id)

        if adapter:
            try:
                from peft import PeftModel
                model = PeftModel.from_pretrained(model, adapter)
                print(f"[worker {os.getpid()}] loaded adapter {adapter}")
            except Exception as e:
                print(f"[worker {os.getpid()}] failed to load adapter {adapter}: {e}")

        print(f"[worker {os.getpid()}] model loaded, holding for {run_seconds}s")
        time.sleep(run_seconds)

    except Exception as e:
        print(f"[worker {os.getpid()}] failed to load model: {e}")


def spawn_pool(num_workers: int, model_id: str | None, adapter: str | None, hold_time: int):
    procs = []
    for _ in range(num_workers):
        p = mp.Process(target=worker_main, args=(model_id, adapter, hold_time))
        p.start()
        procs.append(p)
        time.sleep(0.5)  # stagger loads slightly

    print(f"Spawned {len(procs)} workers. Press Ctrl-C to stop early.")
    try:
        # wait for processes
        for p in procs:
            p.join()
    except KeyboardInterrupt:
        print("Stopping workers...")
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--workers', type=int, default=2)
    p.add_argument('--model', type=str, default=None)
    p.add_argument('--adapter', type=str, default=None)
    p.add_argument('--hold', type=int, default=600)
    args = p.parse_args(argv)

    spawn_pool(args.workers, args.model, args.adapter, args.hold)


if __name__ == '__main__':
    main()
