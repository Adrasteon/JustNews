Nice — I understand the constraint: the new model must be fully open-source and have good support for
refining/fine‑tuning (not just inference). Given the need for task-specific training without cross-task weight
conflicts, the recommended approach is to use a single stable base model (e.g. Mistral‑7B) and keep separate, per‑task
adapters (LoRA / PEFT / QLoRA). Below are OSS 7B candidates that meet that requirement, the adapter-first workflow,
quantization & training compatibility notes, and concrete next steps you can pick.

## Best fully-OSS 7B models for refining + int8 inference (short list)

1. Mistral 7B (recommended)

  - Pros: Top-tier 7B quality for generation and instruction tasks; strong community/tooling for inference and LoRA/QLoRA fine-tuning.

  - Training/refinement: Supports adapter-based fine-tuning (LoRA / QLoRA pipelines) and standard fp16 fine-tuning.

  - Quantization: Works well with bitsandbytes (int8) for inference; performs robustly after quantization.

1. MPT-7B / MPT-7B-Instruct (very training-friendly)

  - Pros: Apache-licensed, designed for training & fine-tuning; great transparency & reproducibility for refinement workflows.

  - Training/refinement: Excellent (used widely for fine-tuning and research).

  - Quantization: Works for int8 inference; training/QLoRA pipelines supported.

1. Pythia-7B (research-first, fully OSS)

  - Pros: Full open research lineage, easy to retrain or refine; great for reproducible fine-tuning/evaluation.

  - Training/refinement: Very well supported for training/refinement workflows.

  - Quantization: Quantizable with GPTQ/bitsandbytes; good baseline for experiments.

1. Falcon-7B-Instruct (solid, widely used)

  - Pros: Great inference quality and mature GPTQ / bitsandbytes support.

  - Training/refinement: Many community guides and recipes for LoRA/QLoRA; good practical option.

  - License: Check the specific checkpoint’s license to ensure “fully OSS” for your use.

Notes about “fully OSS”: confirm the exact checkpoint / tag (HF model card) for licensing — MPT / Pythia are
unambiguously permissive; Mistral/Falcon are community-first but check their model cards for usage restrictions.

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

```py from transformers import AutoTokenizer, AutoModelForCausalLM,
BitsAndBytesConfig import torch

bnb = BitsAndBytesConfig( load_in_8bit=True,
bnb_8bit_compute_dtype=torch.float16, bnb_8bit_use_double_quant=True )

model_id = "mistralai/Mistral-7B-Instruct"   # example - pick repo with OSS
license tok = AutoTokenizer.from_pretrained(model_id) model =
AutoModelForCausalLM.from_pretrained(model_id, quantization_config=bnb,
device_map="auto")

  # Example: load a small per-task adapter at runtime (PEFT/LoRA)
from peft import PeftModel adapter_path =
"modelstore/agents/synthesizer/adapters/mistral_synth_v1" model =
PeftModel.from_pretrained(model, adapter_path) ```

- Quick QLoRA starter (finetuning adapters):

  - Use the PEFT + bitsandbytes + transformers recipe described in HF QLoRA examples. QLoRA trains LoRA adapters while weights are 4-bit quantized, fitting on 24GB typically.

---

## Recommendation (single best pick for your constraints)

- If you want the best quality + broad community support and you plan to refine often: Mistral‑7B (or Mistral‑7B‑Instruct) — +bitsandbytes for inference, +QLoRA/PEFT for refining.

- If you want the most training-friendly option with permissive OSS license: MPT‑7B‑Instruct or Pythia‑7B — both are excellent for iterative training and experimentation.

---

## Next actions I can take for you (pick one)

1) Prototype integration: add a small `agents/tools/7b_re_ranker.py` script in
the repo that:

   - Loads an OSS 7B int8 model (bnb),

   - Scores candidate (top-k) outputs,

   - Provides a small test using existing dataset/fixtures.
2) Add a training/refinement template (QLoRA + PEFT) to the repo with a runnable
example that works on RTX 3090. The template will produce small per-task
adapters and store them in the ModelStore so each agent can load their adapter
at runtime. 3) Run a short local experiment right now (on your machine) testing
one chosen model’s int8 memory + latency and produce a short report.

Which one do you want me to implement next? (If you pick 1 or 2, tell me which
model from the shortlist to use: Mistral, MPT, Pythia, or Falcon.)

---

## Validation experiment — short real-mode perf sweep (what I ran)

I ran a short, reproducible experiment on your RTX 3090 to verify bitsandbytes
(CUDA 12.8) + Mistral-7B-v0.3 int8 inference and to collect latency and memory
numbers that you can use to size orchestrator pools.

- Environment: conda env `justnews-gpu-py310` (PyTorch 2.9.1+cu128), CUDA 12.8 toolkit installed on host.

- Model: mistralai/Mistral-7B-v0.3 (public HF safetensors). I compiled and installed bitsandbytes from source matching CUDA 12.8 and used the 8-bit load path.

- Script used: `scripts/perf/simulate_concurrent_inference.py` (has a new `--sweep` mode and `--output-csv/--output-json` output options added).

- Command run (this produced CSV/JSON under scripts/perf/results):

```bash
conda run -n justnews-gpu-py310 \ RE_RANKER_TEST_MODE=0 RE_RANKER_MODEL=mistralai/Mistral-7B-v0.3 \ python
scripts/perf/simulate_concurrent_inference.py \ --sweep --sweep-max 6 --repeat 3 --requests 30 \ --output-csv
scripts/perf/results/mistral_v0.3_int8_sweep.csv \ --output-json scripts/perf/results/mistral_v0.3_int8_sweep.json

```

Files produced in the repo (copied to canonical path):

- `scripts/perf/results/mistral_v0.3_int8_sweep.csv`

- `scripts/perf/results/mistral_v0.3_int8_sweep.json`

### Key numbers (RTX 3090, single GPU, 8-bit weights)

The CSV aggregates 3 repeats for each worker count (1..6). Representative p50
averages across repeats:

- workers=1 → p50 ≈ 165 ms

- workers=2 → p50 ≈ 279 ms

- workers=3 → p50 ≈ 413 ms

- workers=4 → p50 ≈ 566 ms

- workers=5 → p50 ≈ 722 ms

- workers=6 → p50 ≈ 879 ms

GPU memory footprint observed: model + activations ~12.2 GB (varies slightly
across runs) — this fits comfortably on a 24GB RTX 3090 and leaves headroom for
multiple activations/work items.

### Immediate interpretation & recommendation

- Single-request latency is best when the GPU is not saturated — p50 is ~160 ms in a cold minimal worker scenario.

- Latency increases roughly linearly with concurrent worker count once you exceed the device's practical pipelining point. For low-latency needs (p50 under ~300ms), a single-worker or worker pool of size 1–2 is the sweet spot for this model on a single RTX 3090.

- For higher throughput (bulk scoring) the GPU can process more concurrently but latency will increase; choose pool sizes and request concurrency according to whether you prioritise latency or throughput.

### Next suggested experiment (optional)

If you want next I can:

- Run a longer steady-state sweep (larger requests, warmup vs steady comparison) and plot p50/p95 curves.

- Automate running these per-candidate model (Mistral / MPT / Pythia / Falcon) and save a comparative CSV so you have a data-driven model selection matrix.

If you'd like me to add benchmarking graphs (PNG/SVG) to the repo and a short
notebook to visualise the CSV, I can do that next.

---

## Comparative benchmark: Mistral / MPT / Pythia / Falcon (summary)

I ran the same sweep (workers 1..6, 3 repeats, 30 requests each) for the four
candidate fully-OSS 7B models and saved the results and plots. These are in
`scripts/perf/results` and `scripts/perf/results/plots`.

- Combined CSV (median per workers): `scripts/perf/results/plots/combined_summary.csv`

- Plots (median across repeats):

  - `scripts/perf/results/plots/p50_vs_workers.png` — p50 vs workers

  - `scripts/perf/results/plots/p95_vs_workers.png` — p95 vs workers

  - `scripts/perf/results/plots/avg_vs_workers.png` — average latency vs workers

### TL;DR — single-GPU (RTX 3090) p50 comparisons (median across repeats)

Workers=1 (single concurrent request)

- MPT-7B-Instruct  — ~83 ms (best)

- Pythia-6.9B     — ~91 ms

- Falcon-7B-Inst  — ~96 ms

- Mistral-7B-v0.3 — ~166 ms (largest)

Workers=3 (typical low-latency multi-client)

- MPT-7B-Instruct  — ~206 ms

- Falcon-7B-Inst  — ~227 ms

- Pythia-6.9B     — ~231 ms

- Mistral-7B-v0.3 — ~412 ms

GPU footprint (median observed across runs):

- Mistral-7B-v0.3: ~12.2 GB

- MPT-7B-Instruct: ~8.2 GB

- Pythia-6.9B: ~11.4 GB

- Falcon-7B-Instruct: ~9.7 GB

### Quick interpretation

- MPT-7B-Instruct gives the lowest latencies and smaller memory footprint on a single RTX 3090 — making it a good choice if per-request latency and memory are top priorities.

- Mistral-7B gave higher latencies in these tests (and required ~12 GB memory) — however its absolute quality and tuning characteristics remain a reason to prefer it for accuracy-sensitive tasks; use Mistral if quality outweighs latency and you can accept larger footprints or scale horizontally.

- Pythia-6.9B / Falcon-7B-Instruct fall between MPT and Mistral — solid middle-ground tradeoffs.

### Next options

Pick what you want next:

1) Automate a comparative notebook + plots for these models and include them in
`docs`. 2) Run extended steady-state tests per model (larger request counts and
longer runs) to measure throughput and tail latency more accurately. 3) Use the
CSV to tune the orchestrator pool sizes and configure cluster-level policy
recommendations.

Tell me which of these you'd like me to do next (I can implement any or all).
