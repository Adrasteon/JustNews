import types
import pytest

import agents.analyst.gpu_analyst as ga


def test_gpu_analyst_model_load_instrumentation(monkeypatch):
    # Prepare dummy torch and pipelines
    class DummyCuda:
        def is_available(self):
            return True

        def set_device(self, device):
            pass

        def empty_cache(self):
            pass

        def mem_get_info(self, device):
            # (free, total)
            return (1024**3 * 1, 1024**3 * 2)

        def memory_summary(self):
            return 'summary'

        def device_count(self):
            return 1

    # also register a fake torch module in sys.modules so 'import torch' in code works
    import sys
    dummy_torch = types.SimpleNamespace(cuda=DummyCuda())
    sys.modules['torch'] = dummy_torch
    monkeypatch.setitem(ga.__dict__, 'torch', dummy_torch)
    monkeypatch.setitem(ga.__dict__, 'TORCH_AVAILABLE', True)

    # transformers pipeline stub
    def fake_pipeline(*args, **kwargs):
        return lambda x: [{'label': 'POSITIVE', 'score': 0.9}]

    monkeypatch.setitem(ga.__dict__, 'pipeline', fake_pipeline)
    monkeypatch.setitem(ga.__dict__, 'TRANSFORMERS_AVAILABLE', True)

    # orchestrator client and request_agent_gpu stubs - simulate approval
    class DummyOrchClient:
        def cpu_fallback_decision(self):
            return {"use_gpu": True}
    monkeypatch.setitem(ga.__dict__, 'GPUOrchestratorClient', DummyOrchClient)
    monkeypatch.setitem(ga.__dict__, 'PRODUCTION_GPU_AVAILABLE', True)
    def fake_request_agent_gpu(agent, mem):
        return {"status": "allocated", "gpu_device": 0, "allocated_memory_gb": mem}
    monkeypatch.setitem(ga.__dict__, 'request_agent_gpu', fake_request_agent_gpu)

    events = {}
    def fake_start_event(**meta):
        events['start'] = meta
        return 'evt-1'

    def fake_emit(**meta):
        events.setdefault('instants', []).append(meta)
        return {}

    def fake_end_event(eid, **outcome):
        events['end'] = outcome
        return {}

    monkeypatch.setattr('agents.analyst.gpu_analyst.gpu_metrics.start_event', fake_start_event)
    monkeypatch.setattr('agents.analyst.gpu_analyst.gpu_metrics.emit_instant', fake_emit)
    monkeypatch.setattr('agents.analyst.gpu_analyst.gpu_metrics.end_event', fake_end_event)

    # instantiate and ensure load event happened
    ga.cleanup_gpu_analyst()
    analyst = ga.get_gpu_analyst()
    assert analyst is not None
    # We expect model loaded (sentiment & bias pipelines) and instants were emitted
    assert 'start' in events or (events.get('instants') is not None and any((i.get('operation') == 'gpu_model_init_failed' for i in events.get('instants', []))))
    # cleanup
    analyst.cleanup()
