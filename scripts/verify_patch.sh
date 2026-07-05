#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "$SCRIPT_DIR/common.sh"

need_cmd git
need_cmd python

TARGET_MODE=0
if [[ $# -eq 2 && "$1" == "--target" ]]; then
  TARGET_MODE=1
  shift
fi

[[ $# -eq 1 ]] || die "usage: verify_patch.sh [--target] <run_dir>"

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || die "not_inside_git_repo"
cd "$ROOT"

RUN_DIR="$1"
bash "$SCRIPT_DIR/validate_run_dir.sh" "$RUN_DIR" >/dev/null

CONFIG="$ROOT/gate.toml"
[[ -f "$CONFIG" ]] || die "missing_gate_toml"

RECORD="$RUN_DIR/record.json"
PATCH="$RUN_DIR/patch.diff"
OUT="$RUN_DIR/verify.json"
TARGET_SCOPE_PATH=""

RUN_ID="$(python "$SCRIPT_DIR/json_get.py" "$RECORD" run_id)" || die "missing_run_id"
BASE_SHA="$(python "$SCRIPT_DIR/json_get.py" "$RECORD" base_sha)" || die "missing_base_sha"
RUN_MODE="$(python - "$RECORD" <<'PY'
import json
import sys

record = json.load(open(sys.argv[1], encoding="utf-8"))
print(record.get("run_mode", "forge-local"))
PY
)" || die "invalid_run_mode"

if [[ "$TARGET_MODE" -eq 0 && "$RUN_MODE" == "target" ]]; then
  die "target_mode_requires_explicit_flag"
fi

if [[ "$TARGET_MODE" -eq 1 && "$RUN_MODE" != "target" ]]; then
  die "target_flag_requires_target_run"
fi

REPO_ROOT="$ROOT"
VERIFY_MODE="forge-local"

if [[ "$TARGET_MODE" -eq 1 ]]; then
  TARGET_CONTEXT="$(
    python "$SCRIPT_DIR/target_verify.py" validate-context \
      --record "$RECORD" \
      --config "$CONFIG" \
      --forge-root "$ROOT"
  )" || die "$TARGET_CONTEXT"

  REPO_ROOT="$(printf '%s\n' "$TARGET_CONTEXT" | sed -n 's/^repo_root=//p')"
  BASE_SHA="$(printf '%s\n' "$TARGET_CONTEXT" | sed -n 's/^base_sha=//p')"
  VERIFY_MODE="target"
  TARGET_SCOPE_PATH="$RUN_DIR/allowed-paths.txt"
fi

set +e
python "$SCRIPT_DIR/verifier_worktree.py" verify-detached \
  --repo-root "$REPO_ROOT" \
  --script-dir "$SCRIPT_DIR" \
  --base-sha "$BASE_SHA" \
  --patch "$ROOT/$PATCH" \
  --config "$CONFIG" \
  --verify-mode "$VERIFY_MODE" \
  --scope-file "$TARGET_SCOPE_PATH" \
  --record "$RECORD" \
  --forge-root "$ROOT" \
  --out "$OUT"
VERIFY_STATUS=$?
set -e

case "$VERIFY_STATUS" in
  0) ;;
  10) die "verify_worktree_create_failed" ;;
  20) die "patch_check_failed" ;;
  21) die "patch_apply_failed" ;;
  30) die "verification_failed" ;;
  31) die "patch_outside_target_task_scope" ;;
  *) die "verification_failed" ;;
esac

echo "VERIFY_PATCH: PASS $RUN_ID"
