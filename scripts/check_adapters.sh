#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

if ! command -v git >/dev/null 2>&1; then
  echo "ADAPTER_SMOKE_CHECK: FAIL"
  echo "Reason: missing command: git"
  exit 1
fi

ROOT="$(git -C "$SCRIPT_DIR/.." rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$ROOT" ]]; then
  echo "ADAPTER_SMOKE_CHECK: FAIL"
  echo "Reason: not_inside_git_repo"
  exit 1
fi
cd "$ROOT"

if [[ -n "${USERPROFILE:-}" ]] && command -v cygpath >/dev/null 2>&1; then
  OPENCODE_DIRECT_BIN="$(cygpath -u "$USERPROFILE")/.opencode/bin"
  if [[ -x "$OPENCODE_DIRECT_BIN/opencode.exe" ]]; then
    export PATH="$OPENCODE_DIRECT_BIN:$PATH"
  fi

  CURSOR_AGENT_DIRECT_BIN="$(cygpath -u "$USERPROFILE")/AppData/Local/cursor-agent"
  if [[ -x "$CURSOR_AGENT_DIRECT_BIN/cursor-agent.cmd" ]]; then
    export PATH="$CURSOR_AGENT_DIRECT_BIN:$PATH"
  fi
fi

first_line() {
  tr -d '\r' | sed -n '1p'
}

version_for() {
  local cmd="$1"
  local out=""

  out="$({ "$cmd" --version 2>/dev/null || true; } | first_line)"
  if [[ -z "$out" ]]; then
    out="$({ "$cmd" -V 2>/dev/null || true; } | first_line)"
  fi
  if [[ -z "$out" ]]; then
    out="$({ "$cmd" version 2>/dev/null || true; } | first_line)"
  fi

  printf '%s' "$out"
}

report_script_adapter() {
  local label="$1"
  local path="$2"

  if [[ -x "$path" ]]; then
    echo "$label: available, path=$path"
  else
    echo "$label: missing, path=$path"
  fi
}

report_cli_adapter() {
  local label="$1"
  local command_name="$2"
  local requirement="$3"
  local path=""
  local version=""
  local line=""

  if path="$(command -v "$command_name" 2>/dev/null)"; then
    version="$(version_for "$command_name")"
    line="$label: available"
    if [[ -n "$version" ]]; then
      line="$line, $version"
    fi
    line="$line, path=$path"
    line="$line, $requirement"
    echo "$line"
  else
    line="$label: missing"
    line="$line, $requirement"
    echo "$line"
    if [[ "$requirement" == "required" ]]; then
      return 1
    fi
    return 0
  fi
}

echo "ADAPTER_SMOKE_CHECK: START"
echo

report_script_adapter "manual-simulated-agent" "agents/manual-simulated-agent.sh"
required_cli_missing=0
report_cli_adapter "codex" "codex" "required" || required_cli_missing=1
report_cli_adapter "claude-code" "claude" "required" || required_cli_missing=1
report_cli_adapter "antigravity" "agy" "required"
report_cli_adapter "copilot" "copilot" "required" || required_cli_missing=1
report_cli_adapter "opencode" "opencode" "required" || required_cli_missing=1
report_cli_adapter "cursor" "cursor-agent.cmd" "optional"

if [[ "$required_cli_missing" -ne 0 ]]; then
  echo
  echo "ADAPTER_SMOKE_CHECK: FAIL"
  echo "Reason: required standard adapter CLI unavailable"
  exit 1
fi

echo
echo "ADAPTER_SMOKE_CHECK: PASS"
