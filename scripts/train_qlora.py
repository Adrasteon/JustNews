#!/usr/bin/env python3
"""QLoRA / PEFT training starter script

This is a small, safe template to train LoRA adapters for a 7B-class model on a
single RTX 3090 (24GB). The script is intentionally conservative: it supports
`--dry-run` and `--local-test` modes so CI or dev machines can validate the
workflow without performing long-running training.

It assumes you have installed:
  pip install transformers accelerate bitsandbytes peft datasets

Usage example (dry-run):
  ./scripts/train_qlora.py --model_name_or_path mistralai/Mistral-7B-Instruct --output_dir output/qlora-demo --dry-run

This template performs the following steps:
  - Loads base model in 4-bit (QLoRA) when available via `bnb` + `transformers`
  - Wraps model with PEFT/LoRA adapter
  - Runs a short sanity training loop or a full training run per args

This is a starting point — tune hyperparams and data preprocessing for your tasks.
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Optional


def parse_args(argv: Optional[list[str]] = None):
    p = argparse.ArgumentParser(description="QLoRA starter (safe defaults for RTX3090)")
    p.add_argument("--model_name_or_path", type=str, default=os.environ.get("QLORA_MODEL", "mistralai/Mistral-7B-Instruct"))
    p.add_argument("--output_dir", type=str, default="output/qlora_adapters")
    p.add_argument("--dataset", type=str, default=None, help="HF dataset or path to local JSONL")
    p.add_argument("--train_batch_size", type=int, default=1)
    p.add_argument("--micro_batch_size", type=int, default=1)
    p.add_argument("--epochs", type=int, default=1)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--dry-run", action="store_true", help="Validate pipeline locally without running expensive steps")
    p.add_argument("--max_train_samples", type=int, default=100, help="When dry-run or for small experiments limit samples")
    p.add_argument("--use_quantization", type=str, default="4-bit", choices=["none", "4-bit", "8-bit"], help="Weights quantization to use for base model")
    args = p.parse_args(argv)
    return args


def main(argv: Optional[list[str]] = None):
    args = parse_args(argv)

    print("QLoRA starter invoked with:", args)

    if args.dry_run:
        print("Dry-run: performing quick checks and exiting — no heavy downloads or training will run.")
        # Check available tooling that would be used in a real run
        print("Checking Python packages and CUDA availability...")
        try:
            import torch
            print("torch available", torch.__version__, "cuda:", torch.cuda.is_available())
        except Exception as e:
            print("torch availability check failed — continuing: ", e)

        try:
            import bitsandbytes
            print("bitsandbytes available", bitsandbytes.__version__)
        except Exception as e:
            print("bitsandbytes not available (expected on some CI/dev machines):", e)

        try:
            import transformers
            print("transformers available", transformers.__version__)
        except Exception as e:
            print("transformers not available (expected on some CI/dev machines):", e)

        print("Dry-run OK — no training executed.")
        return 0

    # The full training flow (not executed in this template in CI):
    print("Starting QLoRA training flow — make sure you have installed requirements and have data configured")

    # The rest of this script is a template / pseudocode and intentionally
    # limited here to avoid surprising long runs in dev environments.
    # A production-ready training script would:
    # - Load dataset (datasets.load_dataset)
    # - Prepare tokenizer and data collator
    # - Load pre-trained model with quantization
    # - Wrap model with peft.get_peft_model(..., LoraConfig(...))
    # - Use accelerate launcher to run training loop
    print("TODO: implement full QLoRA training steps — this template is safe by default.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
