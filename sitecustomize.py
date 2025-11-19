import os
import sys
import subprocess

# Run strict preflight checks when running in CI/test context to ensure
# no DeprecationWarnings from older compiled protobuf/upb code are present.
# This file executes early during Python interpreter startup (before most
# imports), ensuring we catch these issues as early as possible.
if os.environ.get('PYTEST_RUNNING') == '1' or os.environ.get('CI') == 'true':
    try:
        py = os.environ.get('PYTHON_BIN', sys.executable)
        r = subprocess.run([py, 'scripts/check_protobuf_version.py'], check=False)
        if r.returncode != 0:
            raise SystemExit('Protobuf version or environment check failed. Run `scripts/check_protobuf_version.py` and follow instructions.')
        r = subprocess.run([py, 'scripts/check_deprecation_warnings.py'], check=False)
        if r.returncode != 0:
            raise SystemExit('Deprecation warnings detected: please upgrade your environment and rebuild any compiled wheels for affected packages (protobuf/upb).')
    except FileNotFoundError:
        print('Warning: preflight check scripts are not available.', file=sys.stderr)