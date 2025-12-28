# Model Adapter Playbook — JustNews

This document captures the design, implementation checklist, and rollout plan for model adapters in the JustNews stack.

Status (short): a shared Mistral adapter wrapper and per-agent adapters are implemented, engines have been wired to use
the shared wrapper, dry-run friendly tests have been added, and a PR-level CI workflow now runs the adapter dry-run
tests inside the canonical conda environment (${CANONICAL_ENV:-justnews-py312}). Adapter unit tests were recently
hardened to assert on behavior (rather than backend-specific SQL traces) so that future adapters stay backend-agnostic.
Option A kicked off: `agents/common/adapter_base.py`now exposes helper dataclasses/utilities (`AdapterResult`,
`AdapterMetadata`,`AdapterHealth`,`AdapterError`) plus lifecycle helpers, and`agents/common/mock_adapter.py` is the
canonical configurable mock used by new/legacy tests. Option C landed: `agents/common/hf_adapter.py` now loads
ModelStore or local checkpoints, supports optional int8/int4 quantization, device-map selection, and dry-run safe
generation defaults. Option B landed: `agents/common/openai_adapter.py` now exposes configurable prompts,
temperature/max token controls, retries/backoff, dry-run short-circuiting, and health/metadata wiring consistent with
BaseAdapter.

It was recorded from an interactive plan created while working in branch `dev/live-run-tests` and includes a recommended
minimal spec, templates, testing and CI suggestions, runtime considerations and next-step options.

---

## 1) What an adapter is

An *adapter* is a small, well-tested component that abstracts a model provider implementation behind a stable interface.
It should:

- hide provider-specific plumbing (OpenAI, HF, local onnx, bitsandbytes)

- handle model load/unload and tokenization

- support synchronous or async inference and batching

- provide health-checks, metrics, and deterministic timeouts

- surface clear errors (AdapterError) so agents can gracefully handle failures

Adapters allow agents and the gpu_orchestrator to be provider-agnostic and easier to test.

## 2) Minimal adapter API contract

Implement a BaseAdapter with these methods (minimal contract):

- load(self, model_id: str, config: dict) -> None

- infer(self, prompt: str, *, max_tokens: int=...) -> dict  # returns { text, tokens, latency, raw }

- batch_infer(self, prompts: list[str], **kwargs) -> list[dict]

- health_check(self) -> bool | dict

- unload(self) -> None

- metadata(self) -> dict  # name, version, device, capacity

Notes for Mistral-style / JSON-centric adapters: per-agent Mistral helpers in this repo also expose convenience methods
(summarize_cluster, classify, review, evaluate_claim, generate_story_brief, analyze, review_content) which standardize
JSON responses for downstream engines. Those extra methods are optional for the generic BaseAdapter, but recommended for
agent adapters that produce structured JSON.

Behavioral details:

- Must be thread-safe or provide documented async entrypoints

- Must accept config from env or injected configuration

- Must implement deterministic timeouts and graceful failure handling

- Emit metrics via existing helpers (latency, success_count, error_count)

Where the repo stands now (examples):

- Shared wrapper: `agents/common/mistral_adapter.py` — a high-level adapter wrapper that handles ModelStore dry-run,
  per-agent delegation and convenience methods.

- Shared base helpers: `agents/common/base_mistral_json_adapter.py` — per-agent helpers build on this for prompt/schema
  enforcement.

- Per-agent helpers: `agents/<agent>/mistral_adapter.py` — agent-specific prompt & JSON-shape helpers (synthesizer,
  analyst, fact_checker, critic, journalist, reasoning, chief_editor, re-ranker, etc.)

- Recommended files you might add:

- `agents/common/adapter_base.py` — base classes & exceptions

- `agents/<agent>/adapters/mock_adapter.py` — mock implementation for CI

- `agents/<agent>/adapters/openai_adapter.py` — API-backed implementation

- `agents/<agent>/adapters/hf_adapter.py` — local HF + accelerate/bnb handler

## 3) Implementation checklist

1. Design + Spec

- Add `agents/common/adapter_base.py`and`docs/adapter_spec.md` with the lifecycle and config.

1. Template & Mock

- Create `MockAdapter`that returns deterministic outputs and supports simulated latency/failures. The repo already
  contains dry-run test helpers and per-agent mocks for JSON shapes; make`agents/common/mock_adapter.py` a canonical
  mock implementation to reuse across agent tests and CI if you pick option A below.

1. Implement one real adapter

- Option A: OpenAI (fastest — needs API key)

- Option B: HuggingFace local (bitsandbytes/accelerate) for on-prem inference

- Option C: litellm or other hosted adapters already in the stack

1. Testing (what's in place and what to add)

- Already added: dry-run focused adapter tests in `tests/adapters/test_mistral_adapter.py`and per-agent dry-run engine
  tests (e.g.`tests/agents/test_*_mistral_engine.py`). These run safely inside the canonical conda env using the project
  wrapper`scripts/dev/run_pytest_conda.sh`.

- CI: a GH Actions workflow was added at `.github/workflows/mistral-dryrun-tests.yml`to run the adapter + engine dry-run
  tests in`${CANONICAL_ENV:-justnews-py312}` on PRs.

- Additional recommendations: add `tests/adapters/test_mock_adapter.py`and`tests/adapters/test_base.py` for the
  BaseAdapter + MockAdapter once created, and include smoke fixtures that exercise JSON schema stability so prompt-
  schema drift is caught by CI.

1. Integrate with orchestrator

- Update `AGENT_MODEL_MAP.json` for mapping

- Add orchestrator logic to schedule adapter.load/unload per GPU plan

1. CI & Canary flows

- Add GH job running adapter unit tests and mock smoke-suite.

## 4) Example adapter sketches

Base class (concept):

```python
class BaseAdapter:
    def load(self, model_id: str, config: dict):
        raise NotImplementedError
    def infer(self, prompt: str, **kwargs):
        raise NotImplementedError
    def batch_infer(self, prompts: list[str], **kwargs):
        raise NotImplementedError
    def health_check(self) -> bool:
        raise NotImplementedError
    def unload(self) -> None:
        raise NotImplementedError

```

OpenAI adapter (brief): wrap the official SDK, add retry/backoff and timeouts, return normalized dicts containing text,
tokens and raw response.

HuggingFace adapter (brief): use transformers + accelerate + bitsandbytes optionally; support load/unload to/from GPU;
provide batch_infer and streaming options if needed.

## 5) Testing & CI plan

- `tests/adapters/test_base.py` — coverage for base behaviour

- `tests/adapters/test_mock_adapter.py` — mock, deterministic behavior

- `tests/adapters/test_openai_adapter.py` — gated by env var or secrets

- GH Actions: run unit + mock smoke; gated job for real providers

## 6) Runtime & deployment notes

- Use `gpu_orchestrator` to control model placement and lifecycle

- Keep adapters light — let orchestrator control resource scheduling

- Use ModelStore for versioned models and signed artifacts
Important runtime caveat (dry-run & ModelStore placeholders):

- The ModelStore loader supports a dry-run mode (MODEL_STORE_DRY_RUN=1 or DRY_RUN=1) which returns lightweight dict
  placeholders instead of real model/tokenizer objects. Per-agent adapter logic must treat those placeholders carefully
  (do not call tokenizer functions if the tokenizer is a dict). The shared `MistralAdapter` wrapper short-circuits heavy
  work in dry-run to protect CI and tests — follow its pattern when writing new adapters.

## 7) Observability & KPIs

- Emit latency histograms, token counters, request successes/errors

- Health endpoints on adapters for quick checks

- Add Grafana panels for adapter latency & error trends

Adapter telemetry — recommendations

- Metrics conventions: adapters should emit the following logical metrics (use the `JustNewsMetrics` helpers):

- `<adapter>_infer_latency_seconds` (histogram) — per-infer latency distribution

- `<adapter>_infer_success` (counter) — successful inference counts

- `<adapter>_infer_errors` (counter) — inference error counts

In this repo we expose these through the existing metrics helper by using `metrics.timing("<name>", value)` and
`metrics.increment("<name>")`. The metrics helper prefixes them with`justnews_custom_*` in Prometheus.

- Grafana dashboard (included): `docs/grafana/adapters-dashboard.json`— import this into Grafana (or use the dashboard
  UID`justnews-adapter-telemetry`) to visualize adapter latency p95, success/error rates and latency distributions
  across adapters.

Alerting (Prometheus rules)

- Prometheus alert rules for adapters are added at `docs/monitoring/adapter-alert-rules.yml` and include:

- adapter_infer_p95_seconds[openai|hf] recording rules

- AdapterOpenAIP95High / AdapterHFP95High when p95 > 2.0s for 5m

- AdapterErrorRateHigh / AdapterErrorRateHighHF when error rate exceeds 5% for 5m

How to wire into monitoring:

1. Add the `docs/monitoring/adapter-alert-rules.yml` group into your Prometheus configuration (additional rule files)
   and reload Prometheus or restart the server.

1. Import `docs/grafana/adapters-dashboard.json` into Grafana (Dashboard -> Import -> Upload JSON, or use provisioning).

1. Tune thresholds as needed for your environment (p95 thresholds are a starting point — heavy models may require higher
   thresholds). Consider adding per-environment overrides (staging vs production).

Suggested on-call actions for alerts:

- p95 high: verify adapter worker pool sizing (GPU memory), model variants (int8 vs FP16), and recent
  deployments/rollouts for regressions.

- error rate high: check provider errors (rate limiting), tokenization errors, and adapter logs for exception spikes.

- CI/Dev note: adapters record basic dry-run metrics (dry-run mode) so CI records are visible in staging when tests run
  in the canonical environment. This makes it easier to monitor for regressions over time.

## 8) Incremental rollout

1. Mock adapter + CI tests

1. OpenAI adapter POC for rapid validation

1. HF-local adapter for cost control (quantized bnb) + orchestrator integration

1. Integration tests & canary e2e runs

1. Production gating and human-in-loop + rollout

## 9) Next immediate steps (pick one)

Notes: a lot of the Mistral-focused infra is implemented already (shared wrapper, per-agent helpers, dry-run tests, CI
hook). The most valuable next small projects are:

- A — Create `agents/common/adapter_base.py`&`agents/common/mock_adapter.py`,
  add`tests/adapters/test_base.py`and`tests/adapters/test_mock_adapter.py`. This will make adapter testing and cross-
  agent unit tests simpler and more consistent. (Recommended / quick win.)

- B — Implement a lightweight OpenAI adapter POC (`agents/common/openai_adapter.py`) and wire a gated test (secrets
  gated) if you want hosted provider coverage.

- C — Implement a reusable HF-local adapter template `agents/common/hf_adapter.py` capable of loading a small local
  quantized model + minimal runner. This requires GPU planning and will be a bigger task.

Implementation templates added (dec 02 2025)

- `agents/common/openai_adapter.py` — a dry-run friendly OpenAI adapter template (lazy import, respects DRY_RUN and
  MODEL_STORE_DRY_RUN, expected to be gated for real runs using OPENAI_API_KEY).

- `agents/common/hf_adapter.py` — HF adapter template (ModelStore-aware loading, optional int8/int4 quantization via
  bitsandbytes, configurable device map, dry-run support, retries/backoff, and helper defaults for generation kwargs).

- `agents/common/adapter_base.py`— shared helpers (`AdapterResult`,`AdapterHealth`,`AdapterMetadata`,`AdapterError`) and
  lifecycle utilities (`mark_loaded`,`ensure_loaded`, shared dry-run detection, default`batch_infer`).

- `agents/common/mock_adapter.py` — canonical deterministic mock adapter with configurable responses, forced failures,
  latency simulation, and health metadata used in CI/unit tests.

Other nice-to-have follow-ups:

- Expand CI to run `tests/adapters/test_base.py`and`tests/adapters/test_mock_adapter.py` on every PR once A is in place.

- Expand CI to run `tests/adapters/*` (base, mock, mistral, openai, hf, fallbacks) on every PR once you want adapter
  coverage increased.

- Document the adapter spec in `docs/adapter_spec.md`and add a quick developer recipe for adding/validating a new per-
  agent adapter (how to stub JSON shapes, how to wire`AGENT_MODEL_MAP.json`, how to test in dry-run + canonical conda
  env).

--- If you'd like I can start with A (base + mock + tests) immediately on branch `dev/live-run-tests` and push the
initial artifacts. If you'd like I can start with A (base + mock + tests) immediately on branch `dev/live-run-tests` and
push the initial artifacts.

## 10) Near-term execution checklist (Dec 2025 refresh)

1. ✅ **Finalize adapter base & mock (Option A)** — done Dec 2, 2025. `agents/common/adapter_base.py`now includes helper
   dataclasses, lifecycle utilities, and behavior-focused defaults;`agents/common/mock_adapter.py`exposes deterministic
   responses, forced-failure hooks, and richer health metadata. Corresponding tests live
   in`tests/adapters/test_adapter_base.py`and`tests/adapters/test_mock_adapter.py`.

1. ✅ **Document adapter spec** — updated `docs/adapter_spec.md` with a developer recipe detailing how to add adapters
   (templates, dry-run guidance, testing, CI steps) so contributors follow the shared contract.

1. ✅ **Broaden CI coverage** — `.github/workflows/mistral-dryrun-tests.yml`now executes the entire`tests/adapters/`suite
   (plus the existing Mistral agent dry-run tests) inside`${CANONICAL_ENV:-justnews-py312}` ensuring new adapters are
   automatically covered.

1. ✅ **Provider expansion (Option C)** — `agents/common/hf_adapter.py`now loads HF/ModelStore checkpoints, handles dry-
   run placeholders, supports optional int8/int4 quantization, exposes configurable generation defaults, and is covered
   by`tests/adapters/test_hf_adapter*.py` plus integration smoke tests.

1. ✅ **Provider expansion (Option B)** — `agents/common/openai_adapter.py`now wraps hosted OpenAI calls with
   configurable system prompt/temperature/max tokens, dry-run simulation, retries/backoff, metrics hooks, and is
   exercised by`tests/adapters/test_openai_adapter*.py` plus gated integration tests.

This ordering keeps the focus on testability first, then documentation, then provider breadth.
