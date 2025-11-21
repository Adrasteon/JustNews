# Conda Environment Backup & Restore

This document explains how to back up and restore the `justnews-v2-py312-fix` conda environment used by the project.

## Why back up the environment
- To ensure reproducible test and CI runs
- To share an exact runtime with collaborators
- To provide a fallback when troubleshooting or reverting

## Artifacts and what they contain
- environment.yml: conda YAML export (usually no-builds) — re-create environment with conda.
- explicit spec: conda explicit spec — exact binary package list (OS-specific).
- pip-freeze.txt: pip packages installed inside environment (optional restore via pip).
- conda-pack tarball: full environment runtime packaged as a `.tar.gz`.

## Commands
- Create artifacts using the helper script (recommended):

```bash
# Back up the conda environment to artifacts/
./scripts/backup_conda_env.sh justnews-v2-py312-fix artifacts
```

- To restore from YAML:

```bash
conda env create -f artifacts/justnews-v2-py312-fix.yml -n justnews-v2-py312-fix-restored
# Optionally: pip install -r artifacts/justnews-v2-py312-fix.pip.txt
```

- To restore from explicit spec (exact binary builds):

```bash
conda create --name justnews-v2-py312-fix-restored --file artifacts/justnews-v2-py312-fix.explicit.txt
```

- To unpack the condapack tarball:

```bash
mkdir -p ~/envs/justnews-v2-py312-fix-unpacked
tar -xzf artifacts/justnews-v2-py312-fix.tar.gz -C ~/envs/justnews-v2-py312-fix-unpacked
~/envs/justnews-v2-py312-fix-unpacked/bin/conda-unpack
```

- Re-run preflight checks and tests after restoring:

```bash
PYTHONPATH=$(pwd) PYTHON_BIN=$(conda run -n justnews-v2-py312-fix-restored --no-capture-output which python) \
    /path/to/python scripts/check_protobuf_version.py
PYTHONPATH=$(pwd) PYTHON_BIN=$(conda run -n justnews-v2-py312-fix-restored --no-capture-output which python) \
    /path/to/python scripts/check_deprecation_warnings.py
```

## Notes
- The `explicit` spec pins precise builds. It is OS-specific — use on the same platform as the original environment.
- If you are using conda-forge packages (recommended), prefer reinstalling or using conda-lock for cross-platform reproducibility.
- After restore, re-run `scripts/check_deprecation_warnings.py`. If it detects deprecation warnings (particularly from `google._upb`), re-install `protobuf` and recompilation-dependent wheels (either with `pip --no-binary` or via the conda package).

## Troubleshooting
- Deprecation warnings caused by compiled extensions imply a mismatch between the runtime’s `upb` and compiled wheels; best approach is to reinstall compatible wheels rather than attempting to mask the warning.
- For CI reproducibility: prefer building or pinning environment from `explicit` specs or `conda-lock` artifacts.
