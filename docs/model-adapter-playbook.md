# Model Adapter Playbook — JustNews

This document captures the design, implementation checklist, and rollout plan for model adapters in the JustNews stack.

It was recorded from an interactive plan created while working in branch `dev/live-run-tests` and includes a recommended minimal spec, templates, testing and CI suggestions, runtime considerations and next-step options.

---

## 1) What an adapter is

An *adapter* is a small, well-tested component that abstracts a model provider implementation behind a stable interface. It should:

- hide provider-specific plumbing (OpenAI, HF, local onnx, bitsandbytes)
- handle model load/unload and tokenization
- support synchronous or async inference and batching
- provide health-checks, metrics, and deterministic timeouts
- surface clear errors (AdapterError) so agents can gracefully handle failures

Adapters allow agents and the gpu_orchestrator to be provider-agnostic and easier to test.

## 2) Minimal adapter API contract

Implement a BaseAdapter with these methods:

- load(self, model_id: str, config: dict) -> None
- infer(self, prompt: str, *, max_tokens: int=...) -> dict  # returns { text, tokens, latency, raw }
- batch_infer(self, prompts: list[str], **kwargs) -> list[dict]
- health_check(self) -> bool | dict
- unload(self) -> None
- metadata(self) -> dict  # name, version, device, capacity

Behavioral details:
- Must be thread-safe or provide documented async entrypoints
- Must accept config from env or injected configuration
- Must implement deterministic timeouts and graceful failure handling
- Emit metrics via existing helpers (latency, success_count, error_count)

File suggestions:
- `agents/common/adapter_base.py` — base classes & exceptions
- `agents/<agent>/adapters/mock_adapter.py` — mock implementation for CI
- `agents/<agent>/adapters/openai_adapter.py` — API-backed implementation
- `agents/<agent>/adapters/hf_adapter.py` — local HF + accelerate/bnb handler

## 3) Implementation checklist

1. Design + Spec
   - Add `agents/common/adapter_base.py` and `docs/adapter_spec.md` with the lifecycle and config.

2. Template & Mock
   - Create `MockAdapter` that returns deterministic outputs and supports simulated latency/failures.

3. Implement one real adapter
   - Option A: OpenAI (fastest — needs API key)
   - Option B: HuggingFace local (bitsandbytes/accelerate) for on-prem inference
   - Option C: litellm or other hosted adapters already in the stack

4. Testing
   - Unit tests for BaseAdapter and MockAdapter
   - Integration tests: run adapter in canonical conda env
   - CI: unit tests + mock-based smoke tests, optional gated real-provider tests with secrets.

5. Integrate with orchestrator
   - Update `AGENT_MODEL_MAP.json` for mapping
   - Add orchestrator logic to schedule adapter.load/unload per GPU plan

6. CI & Canary flows
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

OpenAI adapter (brief): wrap the official SDK, add retry/backoff and timeouts, return normalized dicts containing text, tokens and raw response.

HuggingFace adapter (brief): use transformers + accelerate + bitsandbytes optionally; support load/unload to/from GPU; provide batch_infer and streaming options if needed.

## 5) Testing & CI plan

- `tests/adapters/test_base.py` — coverage for base behaviour
- `tests/adapters/test_mock_adapter.py` — mock, deterministic behavior
- `tests/adapters/test_openai_adapter.py` — gated by env var or secrets
- GH Actions: run unit + mock smoke; gated job for real providers

## 6) Runtime & deployment notes

- Use `gpu_orchestrator` to control model placement and lifecycle
- Keep adapters light — let orchestrator control resource scheduling
- Use ModelStore for versioned models and signed artifacts

## 7) Observability & KPIs

- Emit latency histograms, token counters, request successes/errors
- Health endpoints on adapters for quick checks
- Add Grafana panels for adapter latency & error trends

## 8) Incremental rollout

1. Mock adapter + CI tests
2. OpenAI adapter POC for rapid validation
3. HF-local adapter for cost control (quantized bnb) + orchestrator integration
4. Integration tests & canary e2e runs
5. Production gating and human-in-loop + rollout

## 9) Next immediate steps (pick one)

- A — Create `agents/common/adapter_base.py` & `agents/common/mock_adapter.py` and tests (quick)
- B — Implement OpenAI adapter + tests (fast, needs API keys for gated tests)
- C — Implement local HF adapter template that loads a small model offline (requires GPU resource planning)

---

If you'd like I can start with A (base + mock + tests) immediately on branch `dev/live-run-tests` and push the initial artifacts.
