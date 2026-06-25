#!/usr/bin/env bash
set -Eeuo pipefail

[[ $# -eq 2 ]] || {
  echo "usage: copilot.sh <task_file> <worktree>" >&2
  exit 2
}

TASK_FILE="$1"
WORKTREE="$2"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
python "$SCRIPT_DIR/../scripts/capture_cli_provenance.py" \
  --file "${AXIOM_CLI_PROVENANCE_FILE:-/dev/null}" --command copilot

PROMPT="$(
  {
    echo "You are running inside this isolated disposable git worktree:"
    echo "$WORKTREE"
    echo
    echo "Implement the task below by editing files in that worktree only."
    echo "Do not commit."
    echo "Do not create branches."
    echo "Do not modify files outside this worktree."
    echo "Do not run Axiom Forge runner, qualification, promotion, or test-matrix scripts."
    echo "Do not run tests/runner/run_all.sh."
    echo "Do not run scripts/run_agent_task.sh, scripts/qualify_adapter.sh, scripts/promote.sh, scripts/forge_check.sh, or tests/*/run_all.sh."
    echo "Do not create nested worktrees or invoke agents/bad-*.sh."
    echo
    echo "After editing, stop. Do not wait for further instruction."
    echo
    cat "$TASK_FILE"
  }
)"

copilot \
  -C "$WORKTREE" \
  -p "$PROMPT" \
  --available-tools=view,create,edit \
  --allow-tool=write \
  --disallow-temp-dir \
  --disable-builtin-mcps \
  --no-remote \
  --no-remote-export \
  --no-auto-update \
  --output-format=json
