import subprocess
from pathlib import Path


def run_script(root: Path, apply: bool = False) -> str:
    cmd = ["python3", "scripts/codemods/replace_utcnow.py", "--root", str(root)]
    if apply:
        cmd.append("--apply")
    proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return proc.stdout


def test_dry_run_and_apply(tmp_path: Path):
    # Create several small sample files to exercise the codemod
    f1 = tmp_path / "mod1.py"
    f1.write_text("from datetime import datetime\nnow = datetime.utcnow()\n")

    f2 = tmp_path / "mod2.py"
    f2.write_text("import datetime\nnow = datetime.utcnow()\n")

    f3 = tmp_path / "mod3.py"
    f3.write_text("import datetime as dt\nnow = dt.datetime.utcnow()\n")

    out = run_script(tmp_path, apply=False)
    assert "Found 3 datetime.utcnow() occurrences" in out or "Found 3" in out

    # Apply changes
    out2 = run_script(tmp_path, apply=True)
    assert "Applied replacements to" in out2

    # Validate file contents after apply
    text1 = f1.read_text()
    assert "datetime.now(timezone.utc)" in text1
    assert "from datetime import datetime, timezone" in text1

    text2 = f2.read_text()
    assert "datetime.now(timezone.utc)" in text2
    assert "from datetime import timezone" in text2

    text3 = f3.read_text()
    assert "dt.datetime.now(timezone.utc)" in text3
    assert "from datetime import timezone" in text3
