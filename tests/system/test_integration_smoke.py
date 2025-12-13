import os
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ops" / "integration_smoke_test.sh"


def test_integration_smoke_harness_runs_and_passes(tmp_path, monkeypatch):
    # Ensure PATH contains a fake 'conda' shim (script creates its own shim, but we'll ensure ours is present)
    shim = tmp_path / "conda"
    shim.write_text("""#!/usr/bin/env bash
# minimal shim passthrough
if [ "$1" = "run" ]; then
  shift
  # emulate uvicorn by invoking python built-in server for our test module
  exec /usr/bin/env "$@"
else
  exec /usr/bin/env "$@"
fi
""")
    shim.chmod(0o755)

    # Add the shim directory to PATH
    env = os.environ.copy()
    env["PATH"] = f"{str(tmp_path)}:{env.get('PATH','')}"

    # Run the test harness in repo - it uses manifest_override and local conda shim
    try:
      # Use subprocess-level timeout so tests behave consistently without pytest-timeout plugin.
      completed = subprocess.run([str(SCRIPT)], cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired as exc:
      pytest.fail(f"Integration harness timed out after 120s: {exc}")

    # Print stdout/stderr for debugging (helpful if tests fail)
    print(completed.stdout)
    print(completed.stderr)

    assert completed.returncode == 0, f"Expected success, got {completed.returncode}. Stderr:\n{completed.stderr}"
    assert "Integration Smoke Test: PASS" in completed.stdout
