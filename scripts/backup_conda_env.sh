#!/usr/bin/env bash
set -euo pipefail

# Usage: scripts/backup_conda_env.sh <env_name> <output_dir>
# Default env: justnews-v2-py312
ENV_NAME=${1:-justnews-v2-py312}
OUTDIR=${2:-artifacts}

mkdir -p "$OUTDIR"

echo "Exporting conda environment: $ENV_NAME"
conda env export -n "$ENV_NAME" --no-builds > "$OUTDIR/${ENV_NAME}.yml"
conda list --explicit -n "$ENV_NAME" > "$OUTDIR/${ENV_NAME}.explicit.txt"

# Pack pip-installed packages (if any) from the environment
echo "Exporting pip packages for env: $ENV_NAME"
# Use conda run to avoid changing activated environment in caller
conda run -n "$ENV_NAME" python -m pip freeze --local > "$OUTDIR/${ENV_NAME}.pip.txt"

# Pack entire env if conda-pack is available
if command -v conda-pack >/dev/null 2>&1; then
    echo "Creating condapack tarball for: $ENV_NAME"
    conda pack -n "$ENV_NAME" -o "$OUTDIR/${ENV_NAME}.tar.gz"
else
    echo "Warning: conda-pack not installed. Skipping packed tarball. Use 'conda install -c conda-forge conda-pack' to enable this"
fi

# Output artifacts
ls -l "$OUTDIR"/*${ENV_NAME}* || true

echo "Backup complete: artifacts in $OUTDIR"
