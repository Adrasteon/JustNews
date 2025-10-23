import time

# Preload Job Logic

_MODEL_PRELOAD_STATE = {
    "started_at": None,
    "completed_at": None,
    "in_progress": False,
    "summary": {"total": 0, "done": 0, "failed": 0},
    "per_agent": {},
}


def start_preload_job(agents=None, strict=None):
    """Start the preload job with optional agents and strict mode."""
    _MODEL_PRELOAD_STATE["started_at"] = time.time()
    _MODEL_PRELOAD_STATE["in_progress"] = True
    _MODEL_PRELOAD_STATE["per_agent"] = {agent: {} for agent in (agents or [])}
    # Preserve existing state in summary
    existing_summary = _MODEL_PRELOAD_STATE.get("summary", {"total": 0, "done": 0, "failed": 0})
    _MODEL_PRELOAD_STATE["summary"] = {
        "total": existing_summary["total"] + len(agents or []),
        "done": existing_summary["done"],
        "failed": existing_summary["failed"],
    }

    for agent in (agents or []):
        success, error = _load_agent_model(agent, "test_model", strict)
        if success:
            _MODEL_PRELOAD_STATE["per_agent"][agent] = {"status": "success"}
            _MODEL_PRELOAD_STATE["summary"]["done"] += 1
        else:
            _MODEL_PRELOAD_STATE["per_agent"][agent] = {"status": "error", "error": error}
            _MODEL_PRELOAD_STATE["summary"]["failed"] += 1

    _MODEL_PRELOAD_STATE["in_progress"] = False
    _MODEL_PRELOAD_STATE["completed_at"] = time.time()
    return _MODEL_PRELOAD_STATE


def get_preload_status():
    """Get the status of the preload job."""
    return _MODEL_PRELOAD_STATE


# Correct `_load_agent_model` import
from agents.gpu_orchestrator.utils import _load_agent_model