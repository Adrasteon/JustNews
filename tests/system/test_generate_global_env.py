import os
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPO_ROOT / "infrastructure" / "systemd" / "generate_global_env_from_manifest.sh"


def make_manifest(tmp_path, agents_entries=None, infra_entries=None):
    agents_entries = agents_entries or [
        "mcp_bus|agents.mcp_bus.main:app|8000",
        "test_agent|agents.test_echo.main:app|8765",
    ]
    infra_entries = infra_entries or [
        "grafana|Grafana UI|3000"
    ]
    mfile = tmp_path / "agents_manifest.sh"
    mfile.write_text("""#!/usr/bin/env bash
AGENTS_MANIFEST=(\n" + "\n".join([f'  "{e}"' for e in agents_entries]) + "\n)\n\nINFRA_MANIFEST=(\n" + "\n".join([f'  "{e}"' for e in infra_entries]) + "\n)\n\nexport AGENTS_MANIFEST INFRA_MANIFEST\n""")
    return mfile


@pytest.mark.parametrize("merge_mode,force,existing_port,expected_port", [
    (1, 0, "5406", "5406"),  # merge keeps existing value
    (0, 0, "5406", "3306"),  # no merge uses manifest default
    (1, 1, "5406", "3306"),  # force overrides
])
def test_generate_global_env_merge_and_backup(tmp_path, merge_mode, force, existing_port, expected_port):
    manifest = make_manifest(tmp_path)
    out_file = tmp_path / "global.env"
    # pre-populate out file with MARIADB_PORT that should be respected depending on flags
    out_file.write_text(f"MARIADB_PORT={existing_port}\nMARIADB_HOST=example.com\n")

    # Run generator with MANIFEST_OVERRIDE and appropriate flags
    cmd = [str(GENERATOR), str(out_file)]
    env = os.environ.copy()
    env["MANIFEST_OVERRIDE"] = str(manifest)
    if merge_mode == 0:
        cmd.append("--no-merge")
    if force == 1:
        cmd.append("--force")

    # Default behavior: backup created when BACKUP_MODE=1
    subprocess.check_call(cmd, env=env)

    # Ensure backup exists when BACKUP_MODE is default
    backup_files = list(tmp_path.glob("global.env.bak.*"))
    assert len(backup_files) >= 1

    content = out_file.read_text()
    assert f"MARIADB_HOST=example.com" in content
    assert f"MARIADB_PORT={expected_port}" in content


def test_generate_global_env_respects_manifest_values_by_default(tmp_path):
    manifest = make_manifest(tmp_path, agents_entries=["mcp_bus|agents.mcp_bus.main:app|9000"], infra_entries=["grafana|Grafana UI|3333"])  # custom ports
    out_file = tmp_path / "global.env"
    env = os.environ.copy()
    env["MANIFEST_OVERRIDE"] = str(manifest)

    subprocess.check_call([str(GENERATOR), str(out_file)], env=env)
    content = out_file.read_text()
    assert "MCP_BUS_URL=http://localhost:9000" in content
    assert "GRAFANA_PORT=3333" in content
