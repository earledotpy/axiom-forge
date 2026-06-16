#!/usr/bin/env bash
set -Eeuo pipefail

[[ $# -eq 2 ]] || exit 2

WORKTREE="$2"

cat > "$WORKTREE/app/target.py" <<'PY'
def answer():
    return "bad-commit"
PY

git -C "$WORKTREE" add app/target.py
git -C "$WORKTREE" commit -m "Bad adapter commit"
