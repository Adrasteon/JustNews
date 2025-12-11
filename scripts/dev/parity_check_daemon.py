#!/usr/bin/env python3
"""Parity Check Daemon
Runs `scripts/dev/verify_chroma_parity.py` periodically and optionally performs repair.

Intended for development/staging environments only. Do not enable in production without
appropriate rate-limiting and permission checks.
"""
from __future__ import annotations

import os
import time
import subprocess
import sys
import logging
from datetime import datetime

from common.observability import get_logger

logger = get_logger(__name__)

DEFAULT_INTERVAL = int(os.environ.get('PARITY_CHECK_INTERVAL', 300))  # seconds
REPAIR_ON_MISMATCH = os.environ.get('PARITY_CHECK_REPAIR_ON_MISMATCH', '0') == '1'
VERIFY_SCRIPT = os.path.join(os.path.dirname(__file__), 'verify_chroma_parity.py')


def run_once():
    """Run a single parity check with optional repair.
    Returns True when parity ok or repair successful or False if it failed.
    """
    cmd = [sys.executable, VERIFY_SCRIPT, "--collection", os.environ.get('CHROMADB_COLLECTION', 'articles')]
    if REPAIR_ON_MISMATCH:
        cmd += ["--repair", "--confirm"]
    logger.info("Running parity check: %s", " ".join(cmd))
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = proc.communicate()
    logger.info("Parity check returned %s, stdout:\n%s", proc.returncode, out)
    if err:
        logger.warning("Parity check stderr: %s", err)
    return proc.returncode == 0


def main():
    interval = DEFAULT_INTERVAL
    logger.info("Starting parity check daemon: interval=%s seconds, repair=%s", interval, REPAIR_ON_MISMATCH)
    while True:
        try:
            ok = run_once()
            if not ok:
                logger.warning("Parity check discovered issues (repair may or may not have run). See logs above")
            else:
                logger.info("Parity check passed — no action required")
        except Exception as e:
            logger.error("Parity check daemon error: %s", e)
        # backoff before next run
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("Parity check daemon terminating due to KeyboardInterrupt")
            break


if __name__ == '__main__':
    main()
