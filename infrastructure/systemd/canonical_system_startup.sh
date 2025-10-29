#!/bin/bash
# canonical_system_startup.sh — End-to-end JustNews bring-up helper
# Ensures environment prerequisites, verifies database connectivity,
# validates the shared data mount, and delegates to reset_and_start.sh to
# restart all services followed by a consolidated health check.
#
# Options:
#   --dry-run / --check-only   Run prerequisite checks without restarting services
#   --help                     Display usage information

set -euo pipefail

GLOBAL_ENV_DEFAULT="/etc/justnews/global.env"
DATA_MOUNT_DEFAULT="/media/adra/Data"
RESET_SCRIPT_NAME="reset_and_start.sh"
HEALTH_SCRIPT_NAME="health_check.sh"

DRY_RUN=false
SHOW_USAGE=false
declare -a FORWARDED_ARGS=()

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

usage() {
  cat <<EOF
Usage: canonical_system_startup.sh [--dry-run] [reset_and_start.sh options...]

Performs environment, storage, and database checks, then restarts all JustNews
systemd services via reset_and_start.sh followed by a health summary.

Options:
  --dry-run, --check-only  Validate prerequisites only; do not restart services.
  --help                   Show this message and exit.

All unrecognised options are forwarded directly to reset_and_start.sh.
EOF
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dry-run|--check-only)
        DRY_RUN=true
        shift
        ;;
      --help|-h)
        SHOW_USAGE=true
        shift
        ;;
      *)
        FORWARDED_ARGS+=("$1")
        shift
        ;;
    esac
  done
}

require_root() {
  if [[ $EUID -ne 0 ]]; then
    log_error "Run this script as root (sudo)."
    exit 1
  fi
}

require_command() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    log_error "Required command '$cmd' not found in PATH."
    exit 1
  fi
}

resolve_repo_root() {
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local candidate

  if [[ -n "${JUSTNEWS_ROOT:-}" && -d "$JUSTNEWS_ROOT/agents" ]]; then
    echo "$JUSTNEWS_ROOT"
    return 0
  fi
  if [[ -n "${SERVICE_DIR:-}" && -d "$SERVICE_DIR/agents" ]]; then
    echo "$SERVICE_DIR"
    return 0
  fi
  candidate="$(cd "$script_dir/.." && pwd)"
  if [[ -d "$candidate/agents" ]]; then
    echo "$candidate"
    return 0
  fi
  log_warn "Falling back to repository default path."
  echo "/home/adra/JustNewsAgent-Clean"
}

load_environment() {
  local env_path="${GLOBAL_ENV:-$GLOBAL_ENV_DEFAULT}"
  if [[ ! -f "$env_path" ]]; then
    log_error "Global environment file not found at $env_path"
    exit 1
  fi
  log_info "Loading global environment from $env_path"
  # shellcheck disable=SC1090
  set -a; source "$env_path"; set +a
}

ensure_env_value() {
  local name="$1"
  local value="${!name:-}"
  if [[ -z "$value" ]]; then
    log_error "Required environment variable $name is empty after loading global.env"
    exit 1
  fi
}

check_python_runtime() {
  local python_path="${PYTHON_BIN:-}"
  if [[ ! -x "$python_path" ]]; then
    log_error "Configured PYTHON_BIN '$python_path' does not exist or is not executable"
    exit 1
  fi
  if ! python_version="$($python_path --version 2>&1)"; then
    log_error "Unable to execute PYTHON_BIN ('$python_path --version' failed)"
    exit 1
  fi
  log_success "Python runtime detected: $python_version"
  if [[ "$python_path" != *"justnews-v2-py312"* ]]; then
    log_warn "PYTHON_BIN path does not include 'justnews-v2-py312'; confirm the correct environment is targeted"
  fi
}

check_data_mount() {
  local mount_point="${JUSTNEWS_DATA_MOUNT:-$DATA_MOUNT_DEFAULT}"
  if [[ ! -d "$mount_point" ]]; then
    log_error "Data mount point $mount_point does not exist"
    exit 1
  fi
  if mountpoint -q "$mount_point"; then
    log_success "Data mount $mount_point is mounted"
  else
    if grep -E "^[^#].+\s+$mount_point\s" /etc/fstab >/dev/null 2>&1; then
      log_warn "Data mount $mount_point is not active; attempting to mount via /etc/fstab entry"
      if mount "$mount_point" >/dev/null 2>&1; then
        log_success "Mounted $mount_point successfully"
      else
        log_error "Failed to mount $mount_point automatically. Run 'mount $mount_point' after checking the device."
        exit 1
      fi
    else
      log_error "Data mount $mount_point is not mounted and has no matching /etc/fstab entry"
      exit 1
    fi
  fi
  if [[ -n "${MODEL_STORE_ROOT:-}" ]]; then
    mkdir -p "$MODEL_STORE_ROOT"
    log_info "Ensured MODEL_STORE_ROOT directory $MODEL_STORE_ROOT exists"
  fi
  if [[ -n "${BASE_MODEL_DIR:-}" ]]; then
    mkdir -p "$BASE_MODEL_DIR"
    log_info "Ensured BASE_MODEL_DIR directory $BASE_MODEL_DIR exists"
  fi
}

check_database() {
  require_command psql
  local host="${JUSTNEWS_DB_HOST:-${POSTGRES_HOST:-localhost}}"
  local port="${JUSTNEWS_DB_PORT:-${POSTGRES_PORT:-5432}}"
  local name="${JUSTNEWS_DB_NAME:-${POSTGRES_DB:-justnews}}"
  local user="${JUSTNEWS_DB_USER:-${POSTGRES_USER:-justnews_user}}"
  local password="${JUSTNEWS_DB_PASSWORD:-${POSTGRES_PASSWORD:-password123}}"

  log_info "Verifying connectivity to PostgreSQL database '$name' on $host:$port"
  local output
  if ! output=$(PGPASSWORD="$password" psql -h "$host" -p "$port" -U "$user" -d "$name" -c 'SELECT 1;' 2>&1); then
    log_error "Unable to connect to database $name as $user"
    log_error "psql error: $output"
    log_error "Ensure PostgreSQL is running and credentials in /etc/justnews/global.env are correct."
    log_error "Example manual check: PGPASSWORD=$password psql -h $host -p $port -U $user -d $name"
    exit 1
  fi
  log_success "Database $name is reachable"
}

run_reset_and_start() {
  local repo_root="$1"
  local reset_script="$repo_root/infrastructure/systemd/$RESET_SCRIPT_NAME"
  if [[ ! -x "$reset_script" ]]; then
    log_error "Reset script not executable at $reset_script"
    exit 1
  fi
  log_info "Invoking $RESET_SCRIPT_NAME to restart services"
  shift
  "$reset_script" "$@"
}

run_health_summary() {
  local repo_root="$1"
  local health_script="$repo_root/infrastructure/systemd/$HEALTH_SCRIPT_NAME"
  if [[ -x "$health_script" ]]; then
    log_info "Running consolidated health check"
    if "$health_script"; then
      log_success "Health check completed"
    else
      log_warn "Health check reported issues"
    fi
  else
    log_warn "Health check script not found at $health_script"
  fi
}

main() {
  parse_args "$@"
  if [[ "$SHOW_USAGE" == true ]]; then
    usage
    exit 0
  fi

  require_root
  require_command mountpoint
  require_command mount
  load_environment
  ensure_env_value SERVICE_DIR
  ensure_env_value PYTHON_BIN
  check_python_runtime
  check_data_mount
  check_database

  local repo_root
  repo_root="$(resolve_repo_root)"

  # Gather args destined for reset_and_start while keeping a copy for health logic
  if [[ "$DRY_RUN" == true ]]; then
    log_info "Dry-run requested; skipping service restart"
  else
    run_reset_and_start "$repo_root" "${FORWARDED_ARGS[@]}"
    run_health_summary "$repo_root"
  fi

  if [[ "$DRY_RUN" == true ]]; then
    log_success "Prerequisite checks completed (dry run)"
  else
    log_success "Canonical system startup completed"
  fi
}

main "$@"
