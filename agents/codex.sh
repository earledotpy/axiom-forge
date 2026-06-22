#!/usr/bin/env bash
set -Eeuo pipefail

[[ $# -eq 2 ]] || {
  echo "usage: codex.sh <task_file> <worktree>" >&2
  exit 2
}

TASK_FILE="$1"
WORKTREE="$2"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
python "$SCRIPT_DIR/../scripts/capture_cli_provenance.py" \
  --file "${AXIOM_CLI_PROVENANCE_FILE:-/dev/null}" --command codex

PROMPT="$(
  {
    echo "You are running inside an isolated disposable git worktree."
    echo "Implement the task below by editing files in this worktree only."
    echo "Do not commit."
    echo "Do not create branches."
    echo "Do not modify files outside this worktree."
    echo "Keep the existing tests passing."
    echo
    cat "$TASK_FILE"
  }
)"

codex exec \
  --cd "$WORKTREE" \
  --sandbox workspace-write \
  "$PROMPT"
