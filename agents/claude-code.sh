#!/usr/bin/env bash
set -Eeuo pipefail

[[ $# -eq 2 ]] || {
  echo "usage: claude-code.sh <task_file> <worktree>" >&2
  exit 2
}

TASK_FILE="$1"
WORKTREE="$2"

command -v claude >/dev/null 2>&1 || {
  echo "claude_cli_not_found" >&2
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

cd "$WORKTREE"

claude -p \
  --permission-mode acceptEdits \
  "$PROMPT"
