#!/usr/bin/env bash
set -Eeuo pipefail

[[ $# -eq 2 ]] || {
  echo "usage: antigravity.sh <task_file> <worktree>" >&2
  exit 2
}

TASK_FILE="$1"
WORKTREE="$2"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
python "$SCRIPT_DIR/../scripts/capture_cli_provenance.py" \
  --file "${AXIOM_CLI_PROVENANCE_FILE:-/dev/null}" --command agy

PROMPT="$(
  {
    echo "You are running inside this isolated disposable git worktree:"
    echo "$WORKTREE"
    echo
    echo "Implement the task below by editing files in that worktree only."
    echo "Do not commit."
    echo "Do not create branches."
    echo "Do not modify files outside this worktree."
    echo "Keep the existing tests passing."
    echo
    echo "After editing, stop. Do not wait for further instruction."
    echo
    cat "$TASK_FILE"
  }
)"

cd "$WORKTREE"

agy -p "$PROMPT"
