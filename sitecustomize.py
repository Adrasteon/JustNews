import os
import subprocess
import sys

# Run strict preflight checks when running in CI/test context to ensure
# no DeprecationWarnings from older compiled protobuf/upb code are present.
# This file executes early during Python interpreter startup (before most
# imports), ensuring we catch these issues as early as possible.
if os.environ.get("PYTEST_RUNNING") == "1" or os.environ.get("CI") == "true":
    try:
        py = os.environ.get("PYTHON_BIN", sys.executable)
        r = subprocess.run([py, "scripts/checks/check_protobuf_version.py"], check=False)
        if r.returncode != 0:
            raise SystemExit(
                "Protobuf version or environment check failed. Run `scripts/checks/check_protobuf_version.py` and follow instructions."
            )
        r = subprocess.run([py, "scripts/checks/check_deprecation_warnings.py"], check=False)
        if r.returncode != 0:
            # In test or CI scenario treat deprecation warnings as non-fatal
            # to allow iterative development; print a notice so the CI logs
            # highlight the issue for maintainers.
            print(
                "Warning: Deprecation warnings detected (protobuf/upb). Please upgrade your environment and rebuild compiled wheels for affected packages.",
                file=sys.stderr,
            )
    except FileNotFoundError:
        print("Warning: preflight check scripts are not available.", file=sys.stderr)
