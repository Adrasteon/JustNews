#!/usr/bin/env python3
"""Run a complete live end-to-end 'running order' with persistent per-stage logs and resource snapshots.

This script is intended to run on an isolated staging host (with DEV/PROD-like services available).
It runs stages sequentially and writes durable JSON metadata and logs before moving to the next stage.

Stages used (default): crawl, normalize, parse, editorial, publish, training (optional), knowledge-graph (optional)

Important: run on a dedicated host. Using `--live 1` will attempt to use the real ModelStore and may load heavy models;
use a dedicated host and ensure `MODEL_STORE_ROOT`, DB connection, and GPUs are configured.
"""
from __future__ import annotations

import argparse
import copy
import datetime
import json
import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Reuse the lightweight resource sampler from scripts/dev/resource_monitor.py if available
try:
    from scripts.dev.resource_monitor import sample_once
except Exception:  # pragma: no cover - fallback to internal sampler
    def sample_once():
        return {"ts": time.time(), "note": "no-psutil"}


DEFAULT_STAGES = [
    ("crawl", "python scripts/dev/crawl_canary.py"),
    ("normalize", "python scripts/dev/normalize_canary.py"),
    ("parse", "python scripts/dev/parse_canary.py"),
    ("editorial", "python scripts/dev/editorial_canary.py"),
    ("publish", "python scripts/dev/publish_canary.py"),
]

# Optional stages that may be enabled by flags
OPTIONAL_STAGES = {
    "training": ("training", "python scripts/dev/run_train_example.py --dataset tests/fixtures/train_small"),
    "kg": ("kg", "python agents/knowledge/ingest_test.py --file tests/fixtures/kg_sample.json"),
}


class StageResult:
    def __init__(self, name: str):
        now = time.time()
        self.name = name
        self.start_ts = now
        self.end_ts = None
        self.duration = None
        self.return_code = None
        self.stdout_path = None
        self.stderr_path = None
        self.pre_snapshot = None
        self.post_snapshot = None

    def finish(self, code: int, stdout_path: Path, stderr_path: Path, post_snapshot: dict):
        self.end_ts = time.time()
        self.duration = self.end_ts - self.start_ts
        self.return_code = int(code) if code is not None else None
        self.stdout_path = str(stdout_path)
        self.stderr_path = str(stderr_path)
        self.post_snapshot = post_snapshot

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "start_ts": self.start_ts,
            "end_ts": self.end_ts,
            "duration": self.duration,
            "return_code": self.return_code,
            "stdout_path": self.stdout_path,
            "stderr_path": self.stderr_path,
            "pre_snapshot": self.pre_snapshot,
            "post_snapshot": self.post_snapshot,
        }


def _now_label() -> str:
    return datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")


def run_cmd_capture(cmd: str, cwd: Path, stdout_log: Path, stderr_log: Path, env: Dict[str, str] | None = None, timeout: int | None = None) -> int:
    """Run a shell command with environment, capturing stdout/stderr to files.
    Returns exit code.
    """
    with stdout_log.open("w", encoding="utf-8") as outfh, stderr_log.open("w", encoding="utf-8") as errfh:
        proc = subprocess.Popen(shlex.split(cmd), cwd=str(cwd), stdout=outfh, stderr=errfh, env=env)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            return -2
        return proc.returncode


def _write_metadata(metadata: Dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("output/running_order"), help="Output base dir")
    parser.add_argument("--stages", nargs="*", default=None, help="Optional stage list override (space-separated names)")
    parser.add_argument("--enable-training", action="store_true", help="Enable the training stage")
    parser.add_argument("--enable-kg", action="store_true", help="Enable the KG ingestion stage")
    parser.add_argument("--live", type=int, default=0, help="Set to 1 to run with real models/DBs (default 0: safer dry-run heuristics)")
    parser.add_argument("--timeout", type=int, default=1800, help="Per-stage timeout in seconds (default: 1800)")
    args = parser.parse_args()

    run_label = _now_label()
    base = args.output / run_label
    logs = _ensure_dir(base / "logs")
    trace_file = base / "resource_trace.jsonl"
    metadata_file = base / "metadata.json"

    # persist-run header
    metadata = {
        "run_label": run_label,
        "start_ts": time.time(),
        "live_mode": bool(args.live),
        "stages": [],
        "trace_file": str(trace_file),
    }
    _write_metadata(metadata, metadata_file)

    cwd = Path.cwd()

    # prepare stages list
    stages = copy.deepcopy(DEFAULT_STAGES)
    if args.enable_training:
        stages.append(OPTIONAL_STAGES["training"])
    if args.enable_kg:
        stages.append(OPTIONAL_STAGES["kg"])

    if args.stages:
        # filter to only requested stage names if provided
        allowed_names = set(args.stages)
        stages = [s for s in stages if s[0] in allowed_names]

    # run sequentially and capture per-stage logs + resource snapshots
    for stage_name, stage_cmd in stages:
        print(f"== Starting stage: {stage_name}")
        stage = StageResult(stage_name)

        # sample before
        try:
            stage.pre_snapshot = sample_once()
        except Exception as exc:
            stage.pre_snapshot = {"error": str(exc)}

        stdout_log = logs / f"{stage_name}.stdout.log"
        stderr_log = logs / f"{stage_name}.stderr.log"

        env = os.environ.copy()
        if not args.live:
            env['MODEL_STORE_DRY_RUN'] = '1'

        code = run_cmd_capture(stage_cmd, cwd, stdout_log, stderr_log, env=env, timeout=args.timeout)

        # sample after
        try:
            post = sample_once()
        except Exception as exc:
            post = {"error": str(exc)}

        # ensure logs and resource snapshots are written before metadata is updated
        sys.stdout.flush()
        sys.stderr.flush()

        stage.finish(code, stdout_log, stderr_log, post)
        metadata['stages'].append(stage.to_dict())
        metadata['last_stage'] = stage_name
        metadata['last_code'] = stage.return_code
        metadata['end_ts'] = time.time()

        # write metadata to disk after every stage to ensure persistence
        _write_metadata(metadata, metadata_file)

        # append resource snapshot (note: trace_file is appended as JSONL)
        with trace_file.open('a', encoding='utf-8') as fh:
            fh.write(json.dumps({"stage": stage_name, "pre": stage.pre_snapshot, "post": stage.post_snapshot}) + "\n")

        print(f"== Completed stage: {stage_name} (code={code})")

        if code != 0:
            print(f"Stage {stage_name} failed with code {code}; aborting run. See logs in {logs}")
            return int(code)

    metadata['success'] = True
    metadata['end_ts'] = time.time()
    _write_metadata(metadata, metadata_file)
    print(f"Full-running-order complete. Artifacts saved under {base}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
