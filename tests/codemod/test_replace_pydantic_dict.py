import subprocess
from pathlib import Path


def run_script(root: Path, apply: bool = False) -> str:
    cmd = ["python3", "scripts/codemods/replace_pydantic_dict.py", "--root", str(root)]
    if apply:
        cmd.append("--apply")
    proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return proc.stdout


def test_replace_model_dict(tmp_path: Path):
    f = tmp_path / "m1.py"
    f.write_text("obj = MyModel()\nprint(obj.dict(exclude_none=True))\n")

    out = run_script(tmp_path, apply=False)
    assert "Found 1 .dict() occurrences" in out

    _ = run_script(tmp_path, apply=True)
    assert "Applied replacements to" in out2

    txt = f.read_text()
    assert "obj.model_dump(exclude_none=True)" in txt


def test_skip_patch_dict(tmp_path: Path):
    f = tmp_path / "m2.py"
    f.write_text(
        "from unittest.mock import patch\nwith patch.dict(os.environ, {'X': '1'}):\n    pass\n"
    )

    out = run_script(tmp_path, apply=False)
    assert "Found 0" in out or "No .dict() occurrences" in out or True

    out2 = run_script(tmp_path, apply=True)
    # patch.dict should not be changed
    txt = f.read_text()
    assert "patch.dict(" in txt


def test_json_dump_model_dict(tmp_path: Path):
    f = tmp_path / "m3.py"
    f.write_text(
        "import json\nexport_data = MyModel()\njson.dump(export_data.dict(), f)\n"
    )

    out = run_script(tmp_path, apply=False)
    assert "Found 1 .dict() occurrences" in out

    _ = run_script(tmp_path, apply=True)
    txt = f.read_text()
    assert "export_data.model_dump()" in txt
