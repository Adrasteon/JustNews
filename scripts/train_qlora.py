#!/usr/bin/env python3
"""QLoRA / PEFT training + publishing helper.

This script wires together a reproducible LoRA/QLoRA pipeline plus optional
ModelStore publishing so Phase 2 of the Mistral rollout can be executed with a
single command. The defaults target an RTX 3090 (24GB) and keep conservative
hyper-parameters. Use ``--dry-run`` to validate dependencies or to produce a
stub adapter directory for CI without running a full training loop.

Key capabilities:
    - Loads a causal LM with optional 4-bit or 8-bit quantization via bitsandbytes
    - Applies PEFT/LoRA adapters with configurable rank/alpha/dropout/targets
    - Tokenizes local JSONL files or Hugging Face datasets with an instruction
        template that matches the Mistral Instruct format by default
    - Saves trained adapters (or dry-run stubs) to ``--output_dir`` along with a
        ``training_summary.json`` describing the run
    - When ``--publish`` is supplied, copies the adapter directory into the
        configured ModelStore agent/version so downstream services can pick it up

Example (dry-run + publish metadata only):

.. code-block:: bash

    conda run -n ${CANONICAL_ENV:-justnews-py312} \
         python scripts/train_qlora.py \
             --agent synthesizer \
             --adapter-name mistral_synth_v1 \
             --model_name_or_path mistralai/Mistral-7B-Instruct-v0.3 \
             --train-files data/synth_finetune.jsonl \
             --output_dir output/adapters/mistral_synth_v1 \
             --dry-run

Remove ``--dry-run`` for a real training run (ensure CUDA + bitsandbytes).
"""

import argparse
import json
import os
import shutil
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_PROMPT_TEMPLATE = "<s>[INST] {prompt} [/INST]\n{response}</s>"


@dataclass
class TrainingSummary:
    base_model: str
    agent: str
    adapter_name: str
    adapter_version: str | None
    epochs: int
    learning_rate: float
    gradient_accumulation: int
    quantization: str
    max_seq_length: int
    dataset_name: str | None
    train_files: Sequence[str] | None
    num_samples: int
    timestamp: str
    dry_run: bool


def parse_args(argv: list[str] | None = None):
    p = argparse.ArgumentParser(
        description="Train (Q)LoRA adapters and optionally publish to ModelStore"
    )
    p.add_argument(
        "--agent",
        default="synthesizer",
        help="Agent name to attribute the adapter to (controls ModelStore path)",
    )
    p.add_argument(
        "--adapter-name", help="Logical adapter name (e.g., mistral_synth_v1)"
    )
    p.add_argument(
        "--adapter-version", help="Optional ModelStore version tag (default: timestamp)"
    )
    p.add_argument(
        "--model_name_or_path",
        type=str,
        default=os.environ.get("QLORA_MODEL", "mistralai/Mistral-7B-Instruct-v0.3"),
    )
    p.add_argument("--output_dir", type=str, default="output/qlora_adapters")
    p.add_argument(
        "--dataset-name",
        type=str,
        default=None,
        help="Hugging Face dataset repo to pull (ex: justnews/synth)",
    )
    p.add_argument(
        "--dataset-split",
        type=str,
        default="train",
        help="Split name when using --dataset-name",
    )
    p.add_argument(
        "--train-files",
        nargs="+",
        help="One or more local JSON/JSONL files containing training data",
    )
    p.add_argument(
        "--text-column",
        type=str,
        default=None,
        help="Column holding full prompt+response text",
    )
    p.add_argument(
        "--prompt-column",
        type=str,
        default="prompt",
        help="Column for the prompt/instruction",
    )
    p.add_argument(
        "--response-column",
        type=str,
        default="response",
        help="Column for the ground-truth response",
    )
    p.add_argument(
        "--prompt-template",
        type=str,
        default=DEFAULT_PROMPT_TEMPLATE,
        help="Template applied when formatting prompt/response pairs",
    )
    p.add_argument("--max-seq-length", type=int, default=2048)
    p.add_argument("--train-batch-size", type=int, default=1)
    p.add_argument("--gradient-accumulation", type=int, default=4)
    p.add_argument("--epochs", type=int, default=1)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--warmup-steps", type=int, default=50)
    p.add_argument("--logging-steps", type=int, default=25)
    p.add_argument("--save-steps", type=int, default=200)
    p.add_argument(
        "--max-train-samples",
        type=int,
        default=None,
        help="Optional cap on number of samples fed to training",
    )
    p.add_argument(
        "--use_quantization",
        type=str,
        default="4-bit",
        choices=["none", "4-bit", "8-bit"],
        help="Weights quantization to use for base model",
    )
    p.add_argument("--adapter-r", type=int, default=64)
    p.add_argument("--adapter-alpha", type=int, default=16)
    p.add_argument("--adapter-dropout", type=float, default=0.05)
    p.add_argument(
        "--lora-target-modules",
        type=str,
        default="q_proj,k_proj,v_proj,o_proj",
        help="Comma-separated module list for LoRA",
    )
    p.add_argument("--gradient-checkpointing", action="store_true")
    p.add_argument(
        "--publish",
        action="store_true",
        help="After training, copy the adapter into ModelStore",
    )
    p.add_argument(
        "--model-store-root", type=str, help="Override MODEL_STORE_ROOT when publishing"
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip the expensive training loop; verify dependencies and produce stub artifacts",
    )
    args = p.parse_args(argv)
    if not args.adapter_name:
        if args.dry_run:
            # Give dry-run callers a predictable adapter placeholder so tests/CI can execute without extra CLI args.
            args.adapter_name = f"{args.agent}_dry_run"
        else:
            p.error("--adapter-name is required unless --dry-run is supplied")
    return args


def _lazy_import_train_stack():
    try:
        import torch
        from datasets import load_dataset
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
            DataCollatorForLanguageModeling,
            Trainer,
            TrainingArguments,
        )
    except Exception as exc:  # pragma: no cover - import guard for optional deps
        raise SystemExit(
            "Missing training dependency. Install transformers, datasets, bitsandbytes, peft, accelerate (see docs/model_refactor.md Phase 2)."
        ) from exc
    return {
        "torch": torch,
        "load_dataset": load_dataset,
        "LoraConfig": LoraConfig,
        "get_peft_model": get_peft_model,
        "prepare_model_for_kbit_training": prepare_model_for_kbit_training,
        "AutoModelForCausalLM": AutoModelForCausalLM,
        "AutoTokenizer": AutoTokenizer,
        "BitsAndBytesConfig": BitsAndBytesConfig,
        "DataCollatorForLanguageModeling": DataCollatorForLanguageModeling,
        "Trainer": Trainer,
        "TrainingArguments": TrainingArguments,
    }


def _load_training_dataset(args, load_dataset) -> tuple:
    if args.train_files:
        data_files = {"train": args.train_files}
        dataset = load_dataset("json", data_files=data_files)
        split = dataset["train"]
    elif args.dataset_name:
        split = load_dataset(args.dataset_name, split=args.dataset_split)
    else:
        raise SystemExit(
            "Provide --train-files or --dataset-name so we know what to fine-tune on."
        )

    if args.max_train_samples:
        max_count = min(len(split), args.max_train_samples)
        split = split.select(range(max_count))

    return split, len(split)


def _build_formatter(args) -> Callable[[dict], str]:
    template = args.prompt_template

    def formatter(example: dict) -> str:
        if args.text_column and example.get(args.text_column):
            return str(example[args.text_column])
        prompt = str(example.get(args.prompt_column, "")).strip()
        response = str(example.get(args.response_column, "")).strip()
        if not response:
            raise ValueError(
                "Response column is empty; provide --response-column or --text-column"
            )
        return template.format(prompt=prompt, response=response)

    return formatter


def _tokenize_dataset(dataset, tokenizer, formatter, args):
    def format_record(record):
        return {"text": formatter(record)}

    formatted = dataset.map(
        format_record, remove_columns=dataset.column_names, desc="format prompts"
    )

    def tokenize(batch):
        return tokenizer(
            batch["text"],
            truncation=True,
            max_length=args.max_seq_length,
            padding="max_length",
        )

    tokenized = formatted.map(
        tokenize, batched=True, remove_columns=["text"], desc="tokenize"
    )
    return tokenized


def _prepare_model(args, libs, tokenizer):
    torch = libs["torch"]
    AutoModelForCausalLM = libs["AutoModelForCausalLM"]
    BitsAndBytesConfig = libs["BitsAndBytesConfig"]
    prepare_model_for_kbit_training = libs["prepare_model_for_kbit_training"]
    LoraConfig = libs["LoraConfig"]
    get_peft_model = libs["get_peft_model"]

    quant_cfg = None
    if args.use_quantization == "4-bit":
        quant_cfg = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=getattr(torch, "bfloat16", torch.float16),
            bnb_4bit_use_double_quant=True,
        )
    elif args.use_quantization == "8-bit":
        quant_cfg = BitsAndBytesConfig(load_in_8bit=True)

    print(
        f"Loading base model {args.model_name_or_path} (quantization={args.use_quantization})"
    )
    model = AutoModelForCausalLM.from_pretrained(
        args.model_name_or_path,
        device_map="auto",
        quantization_config=quant_cfg,
        trust_remote_code=True,
    )

    if quant_cfg is not None:
        model = prepare_model_for_kbit_training(model)

    target_modules = [
        m.strip() for m in args.lora_target_modules.split(",") if m.strip()
    ]
    lora_cfg = LoraConfig(
        r=args.adapter_r,
        lora_alpha=args.adapter_alpha,
        target_modules=target_modules or None,
        lora_dropout=args.adapter_dropout,
        bias="none",
        task_type="CAUSAL_LM",
    )

    model = get_peft_model(model, lora_cfg)
    if args.gradient_checkpointing:
        model.gradient_checkpointing_enable()
        model.config.use_cache = False

    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"
    model.resize_token_embeddings(len(tokenizer))
    return model


def _run_training(args, libs, tokenized_dataset, tokenizer):
    torch = libs["torch"]
    Trainer = libs["Trainer"]
    TrainingArguments = libs["TrainingArguments"]
    DataCollatorForLanguageModeling = libs["DataCollatorForLanguageModeling"]

    model = _prepare_model(args, libs, tokenizer)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    training_args = TrainingArguments(
        output_dir=str(output_dir),
        per_device_train_batch_size=args.train_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation,
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        bf16=torch.cuda.is_bf16_supported() if torch.cuda.is_available() else False,
        fp16=not (
            torch.cuda.is_bf16_supported() if torch.cuda.is_available() else False
        ),
        logging_steps=args.logging_steps,
        save_steps=args.save_steps,
        warmup_steps=args.warmup_steps,
        report_to="none",
    )

    collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset,
        data_collator=collator,
    )

    trainer.train()
    print("Training complete. Saving adapter artifacts...")
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    return output_dir


def _write_training_summary(output_dir: Path, summary: TrainingSummary) -> None:
    summary_path = output_dir / "training_summary.json"
    with summary_path.open("w", encoding="utf-8") as fh:
        json.dump(asdict(summary), fh, indent=2)


def _publish_adapter(args, summary: TrainingSummary) -> None:
    root = args.model_store_root or os.environ.get("MODEL_STORE_ROOT")
    if not root:
        raise SystemExit(
            "Publishing requested but MODEL_STORE_ROOT is not set. Pass --model-store-root or export env."
        )
    version = args.adapter_version or f"v{datetime.now(UTC):%Y%m%d-%H%M}"
    from models.model_store import ModelStore

    store = ModelStore(Path(root))
    metadata = {
        "type": "adapter",
        "base_model": summary.base_model,
        "adapter_name": summary.adapter_name,
        "adapter_version": version,
        "agent": summary.agent,
        "training": asdict(summary),
    }

    with store.stage_new(args.agent, version) as tmp_dir:
        target = Path(tmp_dir) / "adapters" / args.adapter_name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(Path(args.output_dir), target)
    store.finalize(args.agent, version, metadata=metadata)
    summary.adapter_version = version
    _write_training_summary(Path(args.output_dir), summary)
    print(f"Published adapter to ModelStore: {store.version_path(args.agent, version)}")


def _dry_run(args) -> TrainingSummary:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    marker = output_dir / "DRY_RUN.txt"
    marker.write_text(
        "Dry-run placeholder. No actual adapter weights produced.\n", encoding="utf-8"
    )
    timestamp = datetime.now(UTC).isoformat()
    summary = TrainingSummary(
        base_model=args.model_name_or_path,
        agent=args.agent,
        adapter_name=args.adapter_name,
        adapter_version=args.adapter_version,
        epochs=args.epochs,
        learning_rate=args.lr,
        gradient_accumulation=args.gradient_accumulation,
        quantization=args.use_quantization,
        max_seq_length=args.max_seq_length,
        dataset_name=args.dataset_name,
        train_files=args.train_files,
        num_samples=args.max_train_samples or 0,
        timestamp=timestamp,
        dry_run=True,
    )
    _write_training_summary(output_dir, summary)
    return summary


def main(argv: list[str] | None = None):
    args = parse_args(argv)
    print("QLoRA helper invoked with:", args)

    if args.dry_run:
        print("Running dry-run checks (no training)...")
        summary = _dry_run(args)
        if args.publish:
            print(
                "Skipping publish because run was a dry-run. Re-run without --dry-run to push artifacts."
            )
        return 0

    libs = _lazy_import_train_stack()
    formatter = _build_formatter(args)
    dataset, sample_count = _load_training_dataset(args, libs["load_dataset"])
    tokenizer = libs["AutoTokenizer"].from_pretrained(
        args.model_name_or_path, use_fast=True
    )
    tokenized = _tokenize_dataset(dataset, tokenizer, formatter, args)

    output_dir = _run_training(args, libs, tokenized, tokenizer)

    summary = TrainingSummary(
        base_model=args.model_name_or_path,
        agent=args.agent,
        adapter_name=args.adapter_name,
        adapter_version=args.adapter_version,
        epochs=args.epochs,
        learning_rate=args.lr,
        gradient_accumulation=args.gradient_accumulation,
        quantization=args.use_quantization,
        max_seq_length=args.max_seq_length,
        dataset_name=args.dataset_name,
        train_files=args.train_files,
        num_samples=sample_count,
        timestamp=datetime.now(UTC).isoformat(),
        dry_run=False,
    )
    _write_training_summary(output_dir, summary)

    if args.publish:
        _publish_adapter(args, summary)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
