#!/usr/bin/env bash
# Wrapper that loads global JustNews environment variables before executing a command.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_SOURCES=(
    "/etc/justnews/global.env"
    "${REPO_ROOT}/global.env"
)

loaded_env="false"
for env_file in "${ENV_SOURCES[@]}"; do
    if [[ -f "${env_file}" ]]; then
        # Export every variable defined in the env file for downstream processes.
        set -a
        # shellcheck disable=SC1090
        source "${env_file}"
        set +a
        loaded_env="true"
        break
    fi
done

if [[ "${loaded_env}" != "true" ]]; then
    echo "WARNING: No global.env file found. Proceeding without loading project env vars." >&2
fi

if [[ $# -eq 0 ]]; then
    echo "Usage: $0 <command> [args...]" >&2
    exit 1
fi

exec "$@"
