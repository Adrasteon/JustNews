import subprocess
import sys
import os
import shutil


def test_no_upb_deprecation_warnings():
    """Run the deprecation check script and assert no deprecation warnings for UPB exist.

    This ensures QA agents and CI fail if third-party compiled C extensions are emitting
    PyType_Spec deprecation warnings at import time.
    """
    py = os.environ.get('PYTHON_BIN')
    if not py or not os.path.exists(py):
        if shutil.which('conda') is not None:
            cmd = ['conda', 'run', '-n', 'justnews-v2-py312', 'python']
        else:
            cmd = [sys.executable]
    else:
        cmd = [py]
    res = subprocess.run(cmd + ['scripts/check_deprecation_warnings.py'])
    assert res.returncode == 0, "Deprecation warnings detected; fix environment and re-run tests"
