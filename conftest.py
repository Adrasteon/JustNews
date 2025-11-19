"""
Top-level pytest conftest to ensure a deterministic test environment across all
test discovery paths (not only `tests/` dir). This sets a minimal test
`global.env` and marks `PYTEST_RUNNING` so test runs don't accidentally
read `/etc/justnews/global.env` on development hosts.
"""
import os
import tempfile
from pathlib import Path
import textwrap
import warnings
from shutil import which
import sys

# Filter known protobuf upb deprecation (PyType_Spec + custom tp_new) in test runs until
# the system environment is upgraded to a protobuf wheel built with the newer API.
import subprocess

# Prefer project-level PYTHON_BIN or a conda env for running preflight scripts; fall
# back to the system python if not available.
project_root = Path(__file__).resolve().parent
project_global_env = project_root / 'global.env'
py_cmd = None
if os.environ.get('PYTHON_BIN'):
    py_cmd = [os.environ.get('PYTHON_BIN')]
elif project_global_env.exists():
    # parse global.env for a PYTHON_BIN or JUSTNEWS_PYTHON entry
    try:
        for line in project_global_env.read_text().splitlines():
            if not line or line.strip().startswith('#'):
                continue
            if line.strip().startswith('PYTHON_BIN='):
                raw_val = line.split('=', 1)[1].strip().strip('"').strip("'")
                # Handle shell-style defaults like ${PYTHON_BIN:-/path}
                if raw_val.startswith('${') and ':-' in raw_val:
                    raw_val = raw_val.split(':-', 1)[1].rstrip('}')
                val = raw_val
                if val:
                    py_cmd = [val]
                    break
            if line.strip().startswith('JUSTNEWS_PYTHON='):
                raw_val = line.split('=', 1)[1].strip().strip('"').strip("'")
                if raw_val.startswith('${') and ':-' in raw_val:
                    raw_val = raw_val.split(':-', 1)[1].rstrip('}')
                val = raw_val
                if val:
                    py_cmd = [val]
                    break
    except Exception:
        py_cmd = None
if py_cmd is None:
    # fallback to using conda run, if available, with the recommended env name
    if which('conda') is not None:
        py_cmd = ['conda', 'run', '-n', 'justnews-v2-py312', 'python']
    else:
        py_cmd = [os.environ.get('PYTHON_BIN', sys.executable or 'python')]

# Enforce environment health: ensure protobuf meets minimum version and no
# upb-related DeprecationWarnings are raised by third-party C extensions.
try:
    result = subprocess.run(py_cmd + ['scripts/check_protobuf_version.py'], check=False)
    if result.returncode != 0:
        raise RuntimeError('protobuf version check failed; please upgrade your environment to protobuf >= 4.24.0 and ensure regenerated wheels for any dependent compiled packages.')
    result = subprocess.run(py_cmd + ['scripts/check_deprecation_warnings.py'], check=False)
    if result.returncode != 0:
        raise RuntimeError('Deprecation warnings detected from third-party compiled extensions (e.g. google._upb._message); please upgrade your environment and reinstall compiled wheels for affected packages.')
except FileNotFoundError:
    # In minimal developer/test environments the scripts may not be available.
    # Print a message and continue; CI should run with the script present to enforce this check.
    print('Warning: preflight check scripts missing. Ensure `scripts/check_protobuf_version.py` and `scripts/check_deprecation_warnings.py` are present in your environment.')

if 'JUSTNEWS_GLOBAL_ENV' not in os.environ:
    tmp_dir = Path(tempfile.gettempdir()) / f"justnews_test_global_env_{os.getpid()}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    env_file = tmp_dir / 'global.env'
    if not env_file.exists():
        env_file.write_text(textwrap.dedent(f"""
        SERVICE_DIR={Path(__file__).resolve().parent}
        PYTHON_BIN={os.environ.get('PYTHON_BIN', '')}
        # Only minimal environment variables are set for tests to avoid
        # unintentionally overriding saved configuration values on reload.
        # Any database-specific environment vars should be explicitly set
        # by tests that require them or by CI when running integration tests.
        """))
    os.environ['JUSTNEWS_GLOBAL_ENV'] = str(env_file)

# Ensure PYTHONPATH is set so top-level `import agents` resolves; prefer the
# repository root or SERVICE_DIR from global.env if present.
os.environ.setdefault('PYTHONPATH', str(project_root))

# Indicate pytest-run for components that check this flag in `env_loader`.
os.environ['PYTEST_RUNNING'] = '1'

# In test runs, disable fatal canonical Chroma validation by default unless a test
# explicitly sets CHROMADB_REQUIRE_CANONICAL via monkeypatch. This prevents
# unrelated unit tests from failing due to environment-level canonical settings.
os.environ.setdefault('CHROMADB_REQUIRE_CANONICAL', '0')
# Disable the embedding module's suppression of upstream warnings during tests so
# our stricter 'no warnings' CI policy can detect and fail on them.
os.environ.setdefault('EMBEDDING_SUPPRESS_WARNINGS', '0')

# Prevent tests from opening real MySQL connections during unit tests.
# Tests that intentionally need a live connector can patch it explicitly.
try:
    import mysql.connector as _mysql_connector  # type: ignore
    from unittest.mock import Mock

    # Replace the `connect` function with a helper that raises by default
    # to ensure code paths fall back to in-memory behavior unless tests
    # explicitly patch `mysql.connector.connect` to provide a fake client.
    def _test_disabled_connect(*args, **kwargs):
        raise _mysql_connector.Error("Database access disabled in unit tests; patch `mysql.connector.connect` to simulate a connection.")

    _mysql_connector.connect = _test_disabled_connect
except Exception:  # pragma: no cover - best-effort during test startup
    pass

# Mock ChromaDB client to avoid making HTTP requests to a local Chroma server
# during unit tests. Tests that need a real client can patch this explicitly.
try:
    import chromadb  # type: ignore
    from unittest.mock import MagicMock as _MagicMock

    chromadb.HttpClient = _MagicMock(name="chromadb.HttpClient")
except Exception:  # pragma: no cover - only relevant when chromadb is present
    pass
