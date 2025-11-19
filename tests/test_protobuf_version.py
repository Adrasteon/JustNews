import subprocess
import sys
import os


def test_protobuf_version_meets_requirement():
    """Ensure protobuf version meets the minimum requirement via the script.

    The script exits non-zero if protobuf version is older than MIN_PROTOBUF.
    """
    py = os.environ.get('PYTHON_BIN', sys.executable)
    res = subprocess.run([py, 'scripts/check_protobuf_version.py'])
    assert res.returncode == 0, "Protobuf version is older than required (>=4.24.0)"
