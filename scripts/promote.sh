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

[[ $# -eq 1 ]] || die "usage: promote.sh [--target] <run_dir>"

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || die "not_inside_git_repo"
cd "$ROOT"

RUN_DIR="$1"
[[ -d "$RUN_DIR" ]] || die "missing_run_dir"

CONFIG="$ROOT/gate.toml"
[[ -f "$CONFIG" ]] || die "missing_gate_toml"

bash "$SCRIPT_DIR/validate_run_dir.sh" "$RUN_DIR" >/dev/null

RECORD="$RUN_DIR/record.json"
PATCH="$RUN_DIR/patch.diff"
PROMOTION_FILE="$RUN_DIR/promotion.json"

RUN_ID="$(python "$SCRIPT_DIR/json_get.py" "$RECORD" run_id)" || die "missing_run_id"
BASE_SHA="$(python "$SCRIPT_DIR/json_get.py" "$RECORD" base_sha)" || die "missing_base_sha"
DEFAULT_BASE="$(python "$SCRIPT_DIR/toml_get.py" "$CONFIG" project.default_base)" || die "malformed_gate_toml"
BRANCH_PREFIX="$(python "$SCRIPT_DIR/toml_get.py" "$CONFIG" promotion.branch_prefix)" || die "malformed_gate_toml"
BRANCH="${BRANCH_PREFIX}${RUN_ID}"
RUN_MODE="$(python - "$RECORD" <<'PY'
import json
import sys

record = json.load(open(sys.argv[1], encoding="utf-8"))
print(record.get("run_mode", "forge-local"))
PY
)" || die "invalid_run_mode"

TARGET_REPO=""
TARGET_NAME=""
TARGET_BASE_BRANCH=""
TARGET_REMOTE_URL=""
DELEGATION_TARGET_BASE_SHA=""
PROMOTION_REPO="$ROOT"
VERIFY_FLAG=()
POST_VERIFY_MODE="forge-local"

if [[ "$TARGET_MODE" -eq 0 && "$RUN_MODE" == "target" ]]; then
  die "target_mode_requires_explicit_flag"
fi

if [[ "$TARGET_MODE" -eq 1 && "$RUN_MODE" != "target" ]]; then
  die "target_flag_requires_target_run"
fi

if [[ "$TARGET_MODE" -eq 1 ]]; then
  TARGET_CONTEXT="$(
    python "$SCRIPT_DIR/target_verify.py" validate-context \
      --record "$RECORD" \
      --config "$CONFIG" \
      --forge-root "$ROOT"
  )" || die "$TARGET_CONTEXT"

  TARGET_REPO="$(printf '%s\n' "$TARGET_CONTEXT" | sed -n 's/^repo_root=//p')"
  BASE_SHA="$(printf '%s\n' "$TARGET_CONTEXT" | sed -n 's/^base_sha=//p')"
  TARGET_NAME="$(python "$SCRIPT_DIR/json_get.py" "$RECORD" target_name)" || die "missing_target_name"
  TARGET_BASE_BRANCH="$(python "$SCRIPT_DIR/json_get.py" "$RECORD" target_base_branch)" || die "missing_target_base_branch"
  TARGET_REMOTE_URL="$(python "$SCRIPT_DIR/json_get.py" "$RECORD" target_remote_url)" || die "missing_target_remote_url"
  DELEGATION_TARGET_BASE_SHA="$BASE_SHA"
  PROMOTION_REPO="$TARGET_REPO"
  VERIFY_FLAG=(--target)
  POST_VERIFY_MODE="target"
fi

GATE_WT=""
BRANCH_CREATED=0
PROMOTION_COMMIT=""
PROMOTION_REVIEW_REVISION=""

record_status() {
  local status="$1"
  local reason="${2:-}"
  python "$SCRIPT_DIR/write_promotion.py" \
    --file "$PROMOTION_FILE" \
    --run-id "$RUN_ID" \
    --status "$status" \
    --reason "$reason" \
    --branch "$BRANCH" \
    --base-sha "$BASE_SHA" \
    --promotion-commit "$PROMOTION_COMMIT" \
    --target-repo "$TARGET_REPO" \
    --target-name "$TARGET_NAME" \
    --target-base-branch "$TARGET_BASE_BRANCH" \
    --delegation-target-base-sha "$DELEGATION_TARGET_BASE_SHA" \
    --target-remote-url "$TARGET_REMOTE_URL" \
    --promotion-review-revision "$PROMOTION_REVIEW_REVISION" \
    >/dev/null 2>&1 || true
}

cleanup_failed() {
  if [[ -n "${GATE_WT:-}" && -d "$GATE_WT" ]]; then
    git -C "$PROMOTION_REPO" worktree remove -f "$GATE_WT" >/dev/null 2>&1 || true
  fi

  if [[ "$BRANCH_CREATED" == "1" ]]; then
    git -C "$PROMOTION_REPO" branch -D "$BRANCH" >/dev/null 2>&1 || true
  fi
}

fail_closed() {
  local reason="$1"
  cleanup_failed
  record_status "FAILED" "$reason"
  echo "PROMOTION FAILED CLOSED: $reason" >&2
  exit 1
}

PROMOTABLE_REASON="$(
  python "$SCRIPT_DIR/run_history.py" check-promotable \
    --record "$RECORD"
)" || fail_closed "$PROMOTABLE_REASON"

if [[ -n "$(git -C "$PROMOTION_REPO" status --porcelain)" ]]; then
  fail_closed "target_repo_dirty"
fi

if [[ "$TARGET_MODE" -eq 1 ]]; then
  CURRENT_TARGET_BRANCH="$(git -C "$PROMOTION_REPO" branch --show-current)" || fail_closed "target_branch_unavailable"
  [[ "$CURRENT_TARGET_BRANCH" == "$TARGET_BASE_BRANCH" ]] || fail_closed "target_not_on_expected_base_branch"
  CURRENT_BASE_SHA="$(git -C "$PROMOTION_REPO" rev-parse "${TARGET_BASE_BRANCH}^{commit}")" || fail_closed "target_base_sha_unresolved"
else
  CURRENT_BASE_SHA="$(git rev-parse "$DEFAULT_BASE")" || fail_closed "default_base_not_found"
fi
if [[ "$TARGET_MODE" -eq 1 ]]; then
  [[ "$DELEGATION_TARGET_BASE_SHA" == "$CURRENT_BASE_SHA" ]] || fail_closed "stale_delegation_target_base"
else
  [[ "$BASE_SHA" == "$CURRENT_BASE_SHA" ]] || fail_closed "stale_base_sha"
fi

git check-ref-format --branch "$BRANCH" >/dev/null 2>&1 || fail_closed "invalid_gate_branch_name"

if git -C "$PROMOTION_REPO" show-ref --verify --quiet "refs/heads/$BRANCH"; then
  fail_closed "gate_branch_already_exists"
fi

bash "$SCRIPT_DIR/verify_patch.sh" "${VERIFY_FLAG[@]}" "$RUN_DIR" || fail_closed "pre_promotion_verification_failed"

PROMOTION_REVIEW_CONTEXT="$(
  python "$SCRIPT_DIR/promotion_review.py" validate \
    --forge-root "$ROOT" \
    --run-dir "$RUN_DIR"
)" || fail_closed "$PROMOTION_REVIEW_CONTEXT"
PROMOTION_REVIEW_REVISION="$(printf '%s\n' "$PROMOTION_REVIEW_CONTEXT" | sed -n 's/^promotion_review_revision=//p')"
[[ -n "$PROMOTION_REVIEW_REVISION" ]] || fail_closed "unresolved_promotion_review_revision"

bash "$SCRIPT_DIR/require_operator_approval.sh" "$RUN_ID" || fail_closed "operator_approval_failed"

GATE_WT="$(mktemp -d)"
rmdir "$GATE_WT"

git -C "$PROMOTION_REPO" worktree add -b "$BRANCH" "$GATE_WT" "$BASE_SHA" >/dev/null || fail_closed "gate_worktree_create_failed"
BRANCH_CREATED=1

set +e
python "$SCRIPT_DIR/verifier_worktree.py" apply-patch \
  --worktree "$GATE_WT" \
  --patch "$ROOT/$PATCH"
PATCH_STATUS=$?
set -e

case "$PATCH_STATUS" in
  0) ;;
  20) fail_closed "gate_patch_check_failed" ;;
  21) fail_closed "gate_patch_apply_failed" ;;
  *) fail_closed "gate_patch_apply_failed" ;;
esac

git -C "$GATE_WT" add -A
git -C "$GATE_WT" commit \
  -m "Promote run $RUN_ID" \
  -m "Source run: $RUN_ID" \
  -m "Base SHA: $BASE_SHA" \
  >/dev/null || fail_closed "promotion_commit_failed"

PROMOTION_COMMIT="$(git -C "$GATE_WT" rev-parse HEAD)" || fail_closed "promotion_commit_lookup_failed"

if [[ "$POST_VERIFY_MODE" == "target" ]]; then
  TARGET_VERIFY_COMMAND=(python "$SCRIPT_DIR/target_verify.py" run \
    --config "$CONFIG" \
    --worktree "$GATE_WT" \
    --out "$RUN_DIR/post_verify.json" \
    --record "$RECORD" \
    --forge-root "$ROOT" \
    --scope-file "$RUN_DIR/allowed-paths.txt")
  if [[ "${OS:-}" == "Windows_NT" ]]; then
    python "$SCRIPT_DIR/run_with_devnull.py" "${TARGET_VERIFY_COMMAND[@]}" \
      || fail_closed "post_promotion_verification_failed"
  else
    "${TARGET_VERIFY_COMMAND[@]}" \
      || fail_closed "post_promotion_verification_failed"
  fi
else
  python "$SCRIPT_DIR/verifier_worktree.py" verify-target \
    --script-dir "$SCRIPT_DIR" \
    --config "$CONFIG" \
    --worktree "$GATE_WT" \
    --out "$RUN_DIR/post_verify.json" \
    || fail_closed "post_promotion_verification_failed"
fi

record_status "PROMOTED" ""

git -C "$PROMOTION_REPO" worktree remove -f "$GATE_WT" >/dev/null 2>&1 || true

echo "PROMOTED: $RUN_ID -> $BRANCH"
echo "COMMIT: $PROMOTION_COMMIT"
