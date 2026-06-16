#!/usr/bin/env bash
set -Eeuo pipefail

[[ $# -eq 2 ]] || exit 2

WORKTREE="$2"
BRANCH_NAME="bad-adapter-branch-$(basename "$WORKTREE")"

git -C "$WORKTREE" switch -c "$BRANCH_NAME"

cat > "$WORKTREE/app/target.py" <<'PY'
def answer():
    return "bad-branch"
PY
