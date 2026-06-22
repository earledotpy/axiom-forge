#!/usr/bin/env bash
set -Eeuo pipefail

[[ $# -eq 2 ]] || exit 2

PARENT_ROOT="${AXIOM_TEST_PARENT_ROOT:-}"
[[ -n "$PARENT_ROOT" ]] || exit 2

mkdir -p "$PARENT_ROOT/tmp"
: > "$PARENT_ROOT/tmp/.axiom-outside-worktree-test"
