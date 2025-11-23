import os
import subprocess


def test_backup_script_dryrun_creates_expected_filenames(tmp_path, monkeypatch):
    # Run the backup script in dry-run mode with a fixed date and capture output
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    script = os.path.join(repo_root, "scripts", "backup_conda_env.sh")

    env = os.environ.copy()
    env["DRY_RUN"] = "1"

    # Use a fixed date for predictable output
    date_str = "20251123"

    result = subprocess.run(
        ["bash", script, "justnews-py312", str(tmp_path), date_str],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )

    out = result.stdout

    # Expect the dry-run messages to reference the date-stamped artifact names
    assert f"{tmp_path}/justnews-py312-{date_str}.yml" in out
    assert f"{tmp_path}/justnews-py312-{date_str}.explicit.txt" in out
    assert f"{tmp_path}/justnews-py312-{date_str}.pip.txt" in out
    assert f"{tmp_path}/justnews-py312-{date_str}.tar.gz" in out or "conda-pack not installed" in out
