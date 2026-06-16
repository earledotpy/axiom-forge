#!/usr/bin/env bash
set -Eeuo pipefail

[[ $# -eq 2 ]] || exit 2

WORKTREE="$2"

git -C "$WORKTREE" switch -c bad-adapter-branch

cat > "$WORKTREE/app/target.py" <<'PY'
def answer():
    return "bad-branch"
PY
