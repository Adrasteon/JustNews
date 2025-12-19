#!/usr/bin/env python3
"""
QLoRA training script for Qwen2-32B on 24GB RTX 3090.
Optimized for low VRAM: NF4 quantization, r=16 LoRA, gradient checkpointing, paged AdamW.
"""
import os
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

import torch
import yaml
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    BitsAndBytesConfig,
    TrainingArguments,
    HfArgumentParser,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer
from datasets import load_dataset


@dataclass
class ModelArguments:
    model_name_or_path: str = field(default="Qwen/Qwen2-32B-Instruct")
    config_path: str = field(default="config/vllm_qwen2_32b.yaml")


@dataclass
class DataArguments:
    train_file: str = field(metadata={"help": "Path to training JSONL file"})
    max_seq_length: int = field(default=2048)


@dataclass
class AdapterArguments:
    agent_name: str = field(metadata={"help": "Agent name (synthesizer, critic, etc.)"})
    adapter_name: str = field(metadata={"help": "Adapter version (qwen2_synth_v1, etc.)"})
    output_dir: str = field(default="output/adapters")
    publish: bool = field(default=False, metadata={"help": "Publish to model_store after training"})


def load_config(config_path: str) -> dict:
    """Load vLLM/training config YAML."""
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def main():
    parser = HfArgumentParser((ModelArguments, DataArguments, AdapterArguments, TrainingArguments))
    model_args, data_args, adapter_args, training_args = parser.parse_args_into_dataclasses()

    # Load config
    config = load_config(model_args.config_path)
    train_cfg = config.get("training", {})

    # BitsAndBytesConfig for NF4 quantization
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16 if train_cfg.get("bf16", True) else torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(
        model_args.model_name_or_path,
        trust_remote_code=True,
        use_fast=True,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Load base model in 4-bit
    print(f"Loading model: {model_args.model_name_or_path} (4-bit NF4)")
    model = AutoModelForCausalLM.from_pretrained(
        model_args.model_name_or_path,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
        torch_dtype=torch.bfloat16 if train_cfg.get("bf16", True) else torch.float16,
    )

    # Prepare for k-bit training (gradient checkpointing, etc.)
    model = prepare_model_for_kbit_training(
        model,
        use_gradient_checkpointing=train_cfg.get("gradient_checkpointing", True),
    )

    # LoRA config
    lora_config = LoraConfig(
        r=train_cfg.get("lora_r", 16),
        lora_alpha=train_cfg.get("lora_alpha", 32),
        lora_dropout=train_cfg.get("lora_dropout", 0.05),
        target_modules=train_cfg.get("lora_target_modules", [
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ]),
        bias="none",
        task_type="CAUSAL_LM",
    )

    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # Load dataset
    dataset = load_dataset("json", data_files=data_args.train_file, split="train")

    # Training arguments
    output_path = Path(adapter_args.output_dir) / adapter_args.agent_name / adapter_args.adapter_name
    output_path.mkdir(parents=True, exist_ok=True)

    training_args.output_dir = str(output_path)
    training_args.per_device_train_batch_size = train_cfg.get("per_device_train_batch_size", 1)
    training_args.gradient_accumulation_steps = train_cfg.get("gradient_accumulation_steps", 16)
    training_args.learning_rate = train_cfg.get("learning_rate", 2e-4)
    training_args.warmup_steps = train_cfg.get("warmup_steps", 100)
    training_args.max_steps = train_cfg.get("max_steps", 1000)
    training_args.bf16 = train_cfg.get("bf16", True)
    training_args.fp16 = False
    training_args.optim = train_cfg.get("optim", "paged_adamw_8bit")
    training_args.logging_steps = 10
    training_args.save_strategy = "steps"
    training_args.save_steps = 200
    training_args.save_total_limit = 2
    training_args.gradient_checkpointing = train_cfg.get("gradient_checkpointing", True)

    # SFTTrainer
    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        tokenizer=tokenizer,
        max_seq_length=data_args.max_seq_length,
        dataset_text_field="text",  # Assumes JSONL has "text" field
        packing=False,
    )

    # Train
    print(f"Starting training for {adapter_args.agent_name}/{adapter_args.adapter_name}")
    trainer.train()

    # Save adapter
    trainer.save_model()
    tokenizer.save_pretrained(str(output_path))
    print(f"Adapter saved to: {output_path}")

    # Publish to model_store
    if adapter_args.publish:
        model_store_root = os.environ.get("MODEL_STORE_ROOT", "/home/adra/JustNews/model_store")
        dest = Path(model_store_root) / "adapters" / adapter_args.agent_name / adapter_args.adapter_name
        dest.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copytree(output_path, dest, dirs_exist_ok=True)
        print(f"Published adapter to: {dest}")


if __name__ == "__main__":
    main()
