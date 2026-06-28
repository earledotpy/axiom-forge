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

set +e
python "$SCRIPT_DIR/verifier_worktree.py" verify-detached \
  --repo-root "$ROOT" \
  --script-dir "$SCRIPT_DIR" \
  --base-sha "$BASE_SHA" \
  --patch "$ROOT/$PATCH" \
  --config "$CONFIG" \
  --out "$OUT"
VERIFY_STATUS=$?
set -e

case "$VERIFY_STATUS" in
  0) ;;
  10) die "verify_worktree_create_failed" ;;
  20) die "patch_check_failed" ;;
  21) die "patch_apply_failed" ;;
  30) die "verification_failed" ;;
  *) die "verification_failed" ;;
esac

echo "VERIFY_PATCH: PASS $RUN_ID"
