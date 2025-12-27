import subprocess
from pathlib import Path


def run_script(root: Path, apply: bool = False) -> str:
    cmd = [
        "python3",
        "scripts/codemods/replace_run_until_complete.py",
        "--root",
        str(root),
    ]
    if apply:
        cmd.append("--apply")
    proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return proc.stdout


def test_get_event_loop_replaced(tmp_path: Path):
    f = tmp_path / "mod1.py"
    f.write_text("import asyncio\nasyncio.get_event_loop().run_until_complete(foo())\n")

    out = run_script(tmp_path, apply=False)
    assert "Found 1 run_until_complete occurrences" in out

    out2 = run_script(tmp_path, apply=True)
    assert "Applied replacements to" in out2

    txt = f.read_text()
    assert "asyncio.run(foo())" in txt


def test_var_loop_new_event_loop_replaced(tmp_path: Path):
    f = tmp_path / "mod2.py"
    f.write_text(
        "import asyncio\nloop = asyncio.new_event_loop()\nloop.run_until_complete(foo())\n"
    )

    out = run_script(tmp_path, apply=False)
    assert "Found 1 run_until_complete occurrences" in out

    out2 = run_script(tmp_path, apply=True)
    assert "Applied replacements to" in out2

    txt = f.read_text()
    assert "asyncio.run(foo())" in txt


def test_var_loop_get_event_loop_replaced(tmp_path: Path):
    f = tmp_path / "mod4.py"
    f.write_text(
        "import asyncio\nloop = asyncio.get_event_loop()\nloop.run_until_complete(foo())\n"
    )

    out = run_script(tmp_path, apply=False)
    assert "Found 1 run_until_complete occurrences" in out

    out2 = run_script(tmp_path, apply=True)
    assert "Applied replacements to" in out2

    txt = f.read_text()
    assert "asyncio.run(foo())" in txt


def test_var_loop_no_new_event_loop_not_replaced(tmp_path: Path):
    f = tmp_path / "mod3.py"
    f.write_text(
        "import asyncio\nloop = some_running_loop\nloop.run_until_complete(foo())\n"
    )

    out = run_script(tmp_path, apply=False)
    assert "Found 1 run_until_complete occurrences" in out

    out2 = run_script(tmp_path, apply=True)
    # Should not apply because there's no new_event_loop in file
    assert (
        "Applied replacements to 0 files" in out2 or "Applied replacements to 0" in out2
    )

    txt = f.read_text()
    assert "loop.run_until_complete(foo())" in txt
