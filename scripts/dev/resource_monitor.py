#!/usr/bin/env python3
"""Lightweight resource monitor for stress runs.

Records system-level and process-level metrics to a JSONL file or CSV for later analysis.
- Samples CPU %, RSS/virtual memory, and top-N processes by RSS
- Attempts to sample GPUs with `nvidia-smi` if available

Intended to run on an isolated staging host while stress tests execute.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

try:
    import psutil
except Exception:  # pragma: no cover - can't depend on psutil in minimal env
    psutil = None  # type: ignore


def sample_gpus() -> List[Dict[str, Any]]:
    try:
        out = subprocess.check_output(shlex.split("nvidia-smi --query-gpu=index,memory.total,memory.used,utilization.gpu --format=csv,noheader,nounits"), text=True)
    except Exception:
        return []
    rows = []
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(',')]
        if len(parts) >= 4:
            try:
                rows.append({
                    'index': int(parts[0]),
                    'mem_total_mb': int(parts[1]),
                    'mem_used_mb': int(parts[2]),
                    'gpu_util_pct': int(parts[3]),
                })
            except Exception:
                continue
    return rows


def sample_processes(top_n: int = 8) -> List[Dict[str, Any]]:
    if psutil is None:
        return []
    procs = []
    for p in psutil.process_iter(['pid', 'name', 'username', 'memory_info', 'cpu_percent', 'create_time', 'cmdline']):
        try:
            info = p.info
            mem = info.get('memory_info')
            procs.append({
                'pid': info.get('pid'),
                'name': info.get('name'),
                'user': info.get('username'),
                'rss_mb': int(mem.rss / 1024 / 1024) if mem else None,
                'cpu_pct': info.get('cpu_percent'),
                'cmdline': ' '.join(info.get('cmdline') or []),
            })
        except Exception:
            continue
    # sort by RSS descending
    procs.sort(key=lambda r: r.get('rss_mb') or 0, reverse=True)
    return procs[:top_n]


def sample_once() -> Dict[str, Any]:
    now = time.time()
    row: Dict[str, Any] = {
        'ts': now,
        'iso': datetime.datetime.utcfromtimestamp(now).isoformat() + 'Z',
        'cpu_percent': None,
        'virtual_memory': None,
        'swap': None,
        'gpus': [],
        'top_processes': [],
    }
    if psutil:
        try:
            row['cpu_percent'] = psutil.cpu_percent(interval=None)
            vm = psutil.virtual_memory()
            row['virtual_memory'] = {'total_mb': int(vm.total / 1024 / 1024), 'used_mb': int(vm.used / 1024 / 1024), 'percent': vm.percent}
            sw = psutil.swap_memory()
            row['swap'] = {'total_mb': int(sw.total / 1024 / 1024), 'used_mb': int(sw.used / 1024 / 1024), 'percent': sw.percent}
            row['top_processes'] = sample_processes()
        except Exception:
            pass
    row['gpus'] = sample_gpus()
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', '-o', type=Path, default=Path('output/resource_trace.jsonl'))
    parser.add_argument('--interval', '-i', type=float, default=2.0, help='Sampling interval seconds (default: 2.0)')
    parser.add_argument('--duration', '-d', type=float, default=300.0, help='Total duration to sample in seconds (default: 300)')
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    end = time.time() + args.duration
    with args.output.open('a') as fh:
        while time.time() < end:
            s = sample_once()
            fh.write(json.dumps(s) + "\n")
            fh.flush()
            time.sleep(args.interval)
    return 0


if __name__ == '__main__':
    sys.exit(main())
