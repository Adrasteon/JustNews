import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# Simple in-memory job store for synthesizer; can be upgraded to MariaDB as needed
class InMemoryJobStore:
    def __init__(self):
        self._store: dict[str, dict[str, Any]] = {}

    def create_job(self, job_id: str, status: str = "pending") -> None:
        self._store[job_id] = {
            "job_id": job_id,
            "status": status,
            "result": None,
            "error": None,
            "created_at": time.time(),
            "updated_at": time.time(),
        }

    def update_status(self, job_id: str, status: str) -> None:
        job = self._store.setdefault(job_id, {})
        job["status"] = status
        job["updated_at"] = time.time()

    def set_result(self, job_id: str, result: Any) -> None:
        job = self._store.setdefault(job_id, {})
        job["result"] = result
        job["status"] = "completed"
        job["updated_at"] = time.time()

    def set_error(self, job_id: str, error: str) -> None:
        job = self._store.setdefault(job_id, {})
        job["error"] = error
        job["status"] = "failed"
        job["updated_at"] = time.time()

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return self._store.get(job_id)


_job_store = InMemoryJobStore()


def create_job(job_id: str) -> None:
    _job_store.create_job(job_id)


def update_status(job_id: str, status: str) -> None:
    _job_store.update_status(job_id, status)


def set_result(job_id: str, result: Any) -> None:
    _job_store.set_result(job_id, result)


def set_error(job_id: str, error: str) -> None:
    _job_store.set_error(job_id, error)


def get_job(job_id: str) -> dict[str, Any] | None:
    return _job_store.get_job(job_id)
