#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "$SCRIPT_DIR/common.sh"

need_cmd git
need_cmd python

[[ $# -eq 1 ]] || die "usage: verify_patch.sh <run_dir>"

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || die "not_inside_git_repo"
cd "$ROOT"

RUN_DIR="$1"
bash "$SCRIPT_DIR/validate_run_dir.sh" "$RUN_DIR" >/dev/null

CONFIG="$ROOT/gate.toml"
[[ -f "$CONFIG" ]] || die "missing_gate_toml"

RECORD="$RUN_DIR/record.json"
PATCH="$RUN_DIR/patch.diff"
OUT="$RUN_DIR/verify.json"

RUN_ID="$(python "$SCRIPT_DIR/json_get.py" "$RECORD" run_id)" || die "missing_run_id"
BASE_SHA="$(python "$SCRIPT_DIR/json_get.py" "$RECORD" base_sha)" || die "missing_base_sha"

VERIFY_WT="$(mktemp -d)"
rmdir "$VERIFY_WT"

cleanup() {
  if [[ -n "${VERIFY_WT:-}" && -d "$VERIFY_WT" ]]; then
    git worktree remove -f "$VERIFY_WT" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

git worktree add --detach "$VERIFY_WT" "$BASE_SHA" >/dev/null || die "verify_worktree_create_failed"

git -C "$VERIFY_WT" apply --check --whitespace=error "$ROOT/$PATCH" || die "patch_check_failed"
git -C "$VERIFY_WT" apply --whitespace=error "$ROOT/$PATCH" || die "patch_apply_failed"

python "$SCRIPT_DIR/verify_target.py" \
  --config "$CONFIG" \
  --worktree "$VERIFY_WT" \
  --out "$OUT" \
  || die "verification_failed"

echo "VERIFY_PATCH: PASS $RUN_ID"
