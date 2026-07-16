#!/usr/bin/env bash
set -Eeuo pipefail

die() {
  echo "ERROR: $*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

safe_run_id() {
  [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$ ]]
}

json_value() {
  local output=""
  local key="$2"
  output="$(python "$SCRIPT_DIR/json_shell_vars.py" extract --file "$1" "$key")" || return
  eval "$output"
  printf '%s\n' "${!key}"
}
