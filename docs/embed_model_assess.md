Nice — I understand the constraint: the new model must be fully open-source and have good support for refining/fine‑tuning (not just inference). Given the need for task-specific training without cross-task weight conflicts, the recommended approach is to use a single stable base model (e.g. Mistral‑7B) and keep separate, per‑task adapters (LoRA / PEFT / QLoRA). Below are OSS 7B candidates that meet that requirement, the adapter-first workflow, quantization & training compatibility notes, and concrete next steps you can pick.

## Best fully-OSS 7B models for refining + int8 inference (short list)

1. Mistral 7B (recommended)
   - Pros: Top-tier 7B quality for generation and instruction tasks; strong community/tooling for inference and LoRA/QLoRA fine-tuning.
   - Training/refinement: Supports adapter-based fine-tuning (LoRA / QLoRA pipelines) and standard fp16 fine-tuning.
   - Quantization: Works well with bitsandbytes (int8) for inference; performs robustly after quantization.

2. MPT-7B / MPT-7B-Instruct (very training-friendly)
   - Pros: Apache-licensed, designed for training & fine-tuning; great transparency & reproducibility for refinement workflows.
   - Training/refinement: Excellent (used widely for fine-tuning and research).
   - Quantization: Works for int8 inference; training/QLoRA pipelines supported.

3. Pythia-7B (research-first, fully OSS)
   - Pros: Full open research lineage, easy to retrain or refine; great for reproducible fine-tuning/evaluation.
   - Training/refinement: Very well supported for training/refinement workflows.
   - Quantization: Quantizable with GPTQ/bitsandbytes; good baseline for experiments.

4. Falcon-7B-Instruct (solid, widely used)
   - Pros: Great inference quality and mature GPTQ / bitsandbytes support.
   - Training/refinement: Many community guides and recipes for LoRA/QLoRA; good practical option.
   - License: Check the specific checkpoint’s license to ensure “fully OSS” for your use.

Notes about “fully OSS”: confirm the exact checkpoint / tag (HF model card) for licensing — MPT / Pythia are unambiguously permissive; Mistral/Falcon are community-first but check their model cards for usage restrictions.

---

## Why these fit your refining & training setup (and the adapter-first approach)

- Support for LoRA / PEFT and QLoRA workflows — lets you refine models without expensive full-weight updates and avoids conflicts when multiple agents need different training.
- Use a single canonical base model (Mistral‑7B recommended) and store small per-agent adapters for each task. Adapters are lightweight, independent, versionable, and hot-swappable at runtime.
- Good compatibility with bitsandbytes / transformers / accelerate on GPU.
- Well-documented training recipes and community tools (AutoTrain, Hugging Face PEFT, QLoRA implementations) so your existing pipeline can plug in easily.

---

## RTX 3090 (24GB) realities — quantization + training

- Inference (int8 via bitsandbytes):
  - 7B int8 typically uses ~6–9 GB VRAM for model weights; fits easily on 24GB plus room for activations.
  - Use load_in_8bit + device_map="auto" + bnb 8bit double quant for best tradeoffs.

- Fine‑tuning / refinement:
  - QLoRA (4-bit weights + LoRA adapters) is the most memory-efficient approach for adapter-style training.
  - RTX 3090 (24GB) can run QLoRA on 7B models for typical adapters and small batch sizes — it’s a common configuration.
  - If you prefer to avoid 4-bit during training because of your 3090 concern: run fp16 fine-tuning (full weights) across a small cluster or offload some to CPU, or use LoRA with fp16 weights.

---

## Practical tooling & commands (what integrates with your repo) — adapter-first

- Required libs: transformers, accelerate, bitsandbytes, peft, evaluate/datasets, (optionally) auto-gptq for GPTQ conversions.
- Sample inference load (int8 with bitsandbytes):
  ```py
  from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
  import torch

  bnb = BitsAndBytesConfig(
    load_in_8bit=True,
    bnb_8bit_compute_dtype=torch.float16,
    bnb_8bit_use_double_quant=True
  )

  model_id = "mistralai/Mistral-7B-Instruct"   # example - pick repo with OSS license
  tok = AutoTokenizer.from_pretrained(model_id)
  model = AutoModelForCausalLM.from_pretrained(model_id, quantization_config=bnb, device_map="auto")

  # Example: load a small per-task adapter at runtime (PEFT/LoRA)
  from peft import PeftModel
  adapter_path = "modelstore/agents/synthesizer/adapters/mistral_synth_v1"
  model = PeftModel.from_pretrained(model, adapter_path)
  ```

- Quick QLoRA starter (finetuning adapters):
  - Use the PEFT + bitsandbytes + transformers recipe described in HF QLoRA examples. QLoRA trains LoRA adapters while weights are 4-bit quantized, fitting on 24GB typically.

---

## Recommendation (single best pick for your constraints)
- If you want the best quality + broad community support and you plan to refine often: Mistral‑7B (or Mistral‑7B‑Instruct) — +bitsandbytes for inference, +QLoRA/PEFT for refining.
- If you want the most training-friendly option with permissive OSS license: MPT‑7B‑Instruct or Pythia‑7B — both are excellent for iterative training and experimentation.

---

## Next actions I can take for you (pick one)
1) Prototype integration: add a small `agents/tools/7b_re_ranker.py` script in the repo that:
   - Loads an OSS 7B int8 model (bnb),
   - Scores candidate (top-k) outputs,
   - Provides a small test using existing dataset/fixtures.
2) Add a training/refinement template (QLoRA + PEFT) to the repo with a runnable example that works on RTX 3090. The template will produce small per-task adapters and store them in the ModelStore so each agent can load their adapter at runtime.
3) Run a short local experiment right now (on your machine) testing one chosen model’s int8 memory + latency and produce a short report.

Which one do you want me to implement next? (If you pick 1 or 2, tell me which model from the shortlist to use: Mistral, MPT, Pythia, or Falcon.)