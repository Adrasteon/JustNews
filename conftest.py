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

# Indicate pytest-run for components that check this flag in `env_loader`.
os.environ['PYTEST_RUNNING'] = '1'

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
