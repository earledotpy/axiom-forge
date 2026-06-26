#!/usr/bin/env bash
set -Eeuo pipefail

[[ $# -eq 2 ]] || {
  echo "usage: kiro.sh <task_file> <worktree>" >&2
  exit 2
}

TASK_FILE="$1"
WORKTREE="$2"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
if [[ -n "${USERPROFILE:-}" ]] && command -v cygpath >/dev/null 2>&1; then
  KIRO_DIRECT_BIN="$(cygpath -u "$USERPROFILE")/AppData/Local/Kiro-Cli"
  if [[ -x "$KIRO_DIRECT_BIN/kiro-cli.exe" ]]; then
    export PATH="$KIRO_DIRECT_BIN:$PATH"
  fi
fi

python "$SCRIPT_DIR/../scripts/capture_cli_provenance.py" \
  --file "${AXIOM_CLI_PROVENANCE_FILE:-/dev/null}" --command kiro-cli.exe

mkdir -p "$WORKTREE/.kiro"
TASK_COPY="$WORKTREE/.kiro/axiom-task.md"
cp "$TASK_FILE" "$TASK_COPY"

PROMPT="You are running inside this isolated disposable git worktree: $WORKTREE. Read the task file at $TASK_COPY and implement it by editing tracked task files in that worktree only. Do not commit. Do not create branches. Do not modify files outside this worktree. Do not run shell commands, git commands, Axiom Forge runner, qualification, promotion, or test-matrix scripts. Do not run tests/runner/run_all.sh. Do not run scripts/run_agent_task.sh, scripts/qualify_adapter.sh, scripts/promote.sh, scripts/forge_check.sh, or tests/*/run_all.sh. Do not create nested worktrees or invoke agents/bad-*.sh. After editing, stop. Do not wait for further instruction."

cd "$WORKTREE"

kiro-cli.exe chat \
  --no-interactive \
  --trust-tools=read,write \
  --wrap never \
  "$PROMPT"
