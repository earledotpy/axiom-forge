#!/usr/bin/env bash
set -Eeuo pipefail

[[ $# -eq 2 ]] || {
  echo "usage: qoder.sh <task_file> <worktree>" >&2
  exit 2
}

TASK_FILE="$1"
WORKTREE="$2"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
if [[ -n "${USERPROFILE:-}" ]] && command -v cygpath >/dev/null 2>&1; then
  QODER_DIRECT_BIN="$(cygpath -u "$USERPROFILE")/.qoder/bin/qodercli"
  if [[ -x "$QODER_DIRECT_BIN/qodercli-1.0.30.exe" ]]; then
    export PATH="$QODER_DIRECT_BIN:$PATH"
  fi
fi

python "$SCRIPT_DIR/../scripts/capture_cli_provenance.py" \
  --file "${AXIOM_CLI_PROVENANCE_FILE:-/dev/null}" --command qodercli-1.0.30.exe

mkdir -p "$WORKTREE/.qoder"
TASK_COPY="$WORKTREE/.qoder/axiom-task.md"
cp "$TASK_FILE" "$TASK_COPY"

PROMPT="You are running inside this isolated disposable git worktree: $WORKTREE. Read the task file at $TASK_COPY and implement it by editing tracked task files in that worktree only. Do not commit. Do not create branches. Do not modify files outside this worktree. Do not run shell commands, git commands, Axiom Forge runner, qualification, promotion, or test-matrix scripts. Do not run tests/runner/run_all.sh. Do not run scripts/run_agent_task.sh, scripts/qualify_adapter.sh, scripts/promote.sh, scripts/forge_check.sh, or tests/*/run_all.sh. Do not create nested worktrees or invoke agents/bad-*.sh. Do not use remote sessions, remote control, worktree creation, MCP servers, plugins, hooks, or external commands. After editing, stop. Do not wait for further instruction."

qodercli-1.0.30.exe \
  --print \
  --cwd "$WORKTREE" \
  --permission-mode accept_edits \
  --tools Read Write Edit Grep Glob \
  --allowed-tools Read \
  --allowed-tools Write \
  --allowed-tools Edit \
  --allowed-tools Grep \
  --allowed-tools Glob \
  --disallowed-tools Bash \
  --disallowed-tools WebFetch \
  --disallowed-tools WebSearch \
  --disallowed-tools Agent \
  --disallowed-tools Mcp \
  --disallowed-tools AskUserQuestion \
  --strict-mcp-config \
  --mcp-config '{"mcpServers":{}}' \
  --output-format json \
  "$PROMPT"
