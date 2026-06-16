#!/usr/bin/env bash
set -Eeuo pipefail

[[ $# -eq 2 ]] || {
  echo "usage: codex.sh <task_file> <worktree>" >&2
  exit 2
}

TASK_FILE="$1"
WORKTREE="$2"

command -v codex >/dev/null 2>&1 || {
  echo "codex_cli_not_found" >&2
  exit 127
}

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
