import subprocess
import sys
import os
import shutil


def test_protobuf_version_meets_requirement():
    """Ensure protobuf version meets the minimum requirement via the script.

    The script exits non-zero if protobuf version is older than MIN_PROTOBUF.
    """
    py = os.environ.get('PYTHON_BIN')
    if not py or not os.path.exists(py):
        if shutil.which('conda') is not None:
            cmd = ['conda', 'run', '-n', 'justnews-py312', 'python']
        else:
            cmd = [sys.executable]
    else:
        cmd = [py]
    res = subprocess.run(cmd + ['scripts/check_protobuf_version.py'])
    assert res.returncode == 0, "Protobuf version is older than required (>=4.24.0)"
