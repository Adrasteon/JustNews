QLoRA / PEFT training template
================================

This document explains the `scripts/train_qlora.py` template in this repository. It is designed to be a safe starting point for finetuning 7B-class open-source models (Mistral, MPT, Pythia, Falcon) on a single RTX 3090 (24GB).

Key points

- The script includes `--dry-run` which validates available tooling without running expensive model downloads or training loops.

- For real runs you will want the following packages installed: `transformers`, `accelerate`, `bitsandbytes`, `peft`, `datasets`.

- For 7B training on RTX 3090 prefer QLoRA (4-bit quantization + LoRA adapters) to fit memory.

Recommended steps to run a small experiment locally (DON'T run on CI without GPU):

1. Create a conda environment with required packages (examples):

```bash
conda create -n qlora python=3.11 -y
conda activate qlora
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install transformers accelerate bitsandbytes peft datasets
```

2. Run a dry-run to check everything:

```bash
./scripts/train_qlora.py --dry-run
```

3. To run a very small local test on a tiny dataset, set `--dataset` to a small HF dataset and run with `--epochs 1` and `--train_batch_size 1`.

Notes on training

- QLoRA recipes require special care with attention to checkpointing and adapter storage. Store LoRA adapters in `--output_dir` so they can be loaded separately from base weights.

- Validate resulting adapter performance on held-out retrieval/re-ranking tasks.
