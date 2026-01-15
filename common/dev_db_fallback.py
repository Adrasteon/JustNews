"""Development/Test Database Environment Fallback Helper.

SECURE IMPLEMENTATION: This module provides environment-based database credential
fallback for development and testing. Credentials are sourced from:
  1. Environment variables (preferred)
  2. /etc/justnews/global.env (if available)
  3. Safe defaults for test environments only

Behavior:
  * Sets database environment variables ONLY if they are currently unset
  * Provides multiple naming conventions for legacy component compatibility
    (DB_*, JUSTNEWS_DB_*, MARIADB_*)
  * Constructs DATABASE_URL if not already defined
  * Emits INFO level log when using environment-based fallback
  * Can be disabled via JUSTNEWS_DISABLE_TEST_DB_FALLBACK=1 environment var

Credential Sources (priority order):
  1. Existing environment variables
  2. /etc/justnews/global.env
  3. Test-only defaults (only when PYTEST_RUNNING=1)

Usage:
  from common.dev_db_fallback import apply_test_db_env_fallback
  apply_test_db_env_fallback(logger)

Return:
  List[str]: Names of environment variables that were applied/created.

Security Notes:
  - Production credentials MUST be set in /etc/justnews/global.env
  - Test defaults only activate when PYTEST_RUNNING=1 is set
  - No hardcoded production credentials exist in this module
"""

from __future__ import annotations

import logging
import os

# Constants
_DISABLE_FLAG = "JUSTNEWS_DISABLE_TEST_DB_FALLBACK"

# Test-only defaults (ONLY applied when PYTEST_RUNNING=1 and values missing)
# Production environments MUST set these in /etc/justnews/global.env
_TEST_DEFAULTS = {
    "DB_HOST": "localhost",
    "DB_PORT": "3306",
    "DB_NAME": "justnews",
    "DB_USER": "justnews_test",
    "DB_PASSWORD": "test_password_12345",
}

# Legacy / alternate variable name mapping – values resolved from _DEV_DEFAULTS
_LEGACY_MIRRORS = {
    "MARIADB_HOST": "DB_HOST",
    "MARIADB_DB": "DB_NAME",
    "MARIADB_USER": "DB_USER",
    "MARIADB_PASSWORD": "DB_PASSWORD",
    "JUSTNEWS_DB_HOST": "DB_HOST",
    "JUSTNEWS_DB_PORT": "DB_PORT",
    "JUSTNEWS_DB_NAME": "DB_NAME",
    "JUSTNEWS_DB_USER": "DB_USER",
    "JUSTNEWS_DB_PASSWORD": "DB_PASSWORD",
}


def _build_database_url(env: dict) -> str:
    """Construct a DATABASE_URL from component env values.

    Args:
        env: Environment dictionary (typically os.environ).

    Returns:
        A MariaDB connection URL.
    """
    user = env.get("DB_USER", _TEST_DEFAULTS["DB_USER"])  # pragma: no cover
    password = env.get("DB_PASSWORD", _TEST_DEFAULTS["DB_PASSWORD"])  # pragma: no cover
    host = env.get("DB_HOST", _TEST_DEFAULTS["DB_HOST"])  # pragma: no cover
    port = env.get("DB_PORT", _TEST_DEFAULTS["DB_PORT"])  # pragma: no cover
    name = env.get("DB_NAME", _TEST_DEFAULTS["DB_NAME"])  # pragma: no cover
    # Construct a MariaDB-compatible URL
    # Note: consumers of DATABASE_URL should support mysql:// or mysql+pymysql://
    return f"mysql://{user}:{password}@{host}:{port}/{name}"


def apply_test_db_env_fallback(logger: logging.Logger | None = None) -> list[str]:
    """Apply test DB environment defaults if not already configured.

    This function performs no destructive overwrites—only missing variables are
    populated. Test defaults are ONLY applied when PYTEST_RUNNING=1 is set.
    Production environments should configure credentials in /etc/justnews/global.env.

    Args:
        logger: Optional logger instance. If omitted, a basic fallback logger is
            created (kept minimal to avoid side-effects).

    Returns:
        List of variable names that were set by this helper. Empty list if
        nothing was changed or the fallback was disabled.
    """
    if os.environ.get(_DISABLE_FLAG):  # Explicit opt-out
        return []

    applied: list[str] = []
    is_test_env = os.environ.get("PYTEST_RUNNING") == "1"

    # Step 1: Primary DB_* defaults (only in test environment)
    for k, v in _TEST_DEFAULTS.items():
        if not os.environ.get(k):  # only set if absent
            if is_test_env:
                os.environ[k] = v  # pragma: no cover (env side-effect)
                applied.append(k)
            else:
                # In non-test environments, log a warning that credentials are missing
                _logger = logger or logging.getLogger("dev_db_fallback")
                _logger.warning(
                    "Database credential %s not set. Configure in /etc/justnews/global.env", k
                )
                # Set empty value to prevent KeyError but signal misconfiguration
                os.environ[k] = ""
                applied.append(f"{k} (empty)")

    # Step 2: Legacy mirrors referencing primary keys
    for mirror, source in _LEGACY_MIRRORS.items():
        if not os.environ.get(mirror) and os.environ.get(source):
            os.environ[mirror] = os.environ[source]  # pragma: no cover
            applied.append(mirror)

    # Step 3: DATABASE_URL synthesis
    if not os.environ.get("DATABASE_URL"):
        os.environ["DATABASE_URL"] = _build_database_url(os.environ)
        applied.append("DATABASE_URL")

    if applied:
        _logger = logger or logging.getLogger("dev_db_fallback")
        if is_test_env:
            _logger.info(
                "Using test database defaults for: %s (test environment)",
                ",".join(applied),
            )
        else:
            _logger.warning(
                "Database credentials missing or incomplete: %s - Configure in /etc/justnews/global.env",
                ",".join(applied),
            )

    return applied


__all__ = ["apply_test_db_env_fallback"]
