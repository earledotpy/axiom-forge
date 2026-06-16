#!/usr/bin/env bash
set -Eeuo pipefail

[[ $# -eq 2 ]] || {
  echo "usage: antigravity.sh <task_file> <worktree>" >&2
  exit 2
}

TASK_FILE="$1"
WORKTREE="$2"

command -v agy >/dev/null 2>&1 || {
  echo "agy_cli_not_found" >&2
  exit 127
}

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
