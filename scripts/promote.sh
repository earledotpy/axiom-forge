#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "$SCRIPT_DIR/common.sh"

need_cmd git
need_cmd python

[[ $# -eq 1 ]] || die "usage: promote.sh <run_dir>"

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

GATE_WT=""
BRANCH_CREATED=0
PROMOTION_COMMIT=""

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
    >/dev/null 2>&1 || true
}

cleanup_failed() {
  if [[ -n "${GATE_WT:-}" && -d "$GATE_WT" ]]; then
    git worktree remove -f "$GATE_WT" >/dev/null 2>&1 || true
  fi

  if [[ "$BRANCH_CREATED" == "1" ]]; then
    git branch -D "$BRANCH" >/dev/null 2>&1 || true
  fi
}

fail_closed() {
  local reason="$1"
  cleanup_failed
  record_status "FAILED" "$reason"
  echo "PROMOTION FAILED CLOSED: $reason" >&2
  exit 1
}

if [[ -n "$(git status --porcelain)" ]]; then
  fail_closed "target_repo_dirty"
fi

CURRENT_BASE_SHA="$(git rev-parse "$DEFAULT_BASE")" || fail_closed "default_base_not_found"
[[ "$BASE_SHA" == "$CURRENT_BASE_SHA" ]] || fail_closed "stale_base_sha"

git check-ref-format --branch "$BRANCH" >/dev/null 2>&1 || fail_closed "invalid_gate_branch_name"

if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  fail_closed "gate_branch_already_exists"
fi

bash "$SCRIPT_DIR/verify_patch.sh" "$RUN_DIR" || fail_closed "pre_promotion_verification_failed"

bash "$SCRIPT_DIR/require_operator_approval.sh" "$RUN_ID" || fail_closed "operator_approval_failed"

GATE_WT="$(mktemp -d)"
rmdir "$GATE_WT"

git worktree add -b "$BRANCH" "$GATE_WT" "$BASE_SHA" >/dev/null || fail_closed "gate_worktree_create_failed"
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

python "$SCRIPT_DIR/verifier_worktree.py" verify-target \
  --script-dir "$SCRIPT_DIR" \
  --config "$CONFIG" \
  --worktree "$GATE_WT" \
  --out "$RUN_DIR/post_verify.json" \
  || fail_closed "post_promotion_verification_failed"

record_status "PROMOTED" ""

git worktree remove -f "$GATE_WT" >/dev/null 2>&1 || true

echo "PROMOTED: $RUN_ID -> $BRANCH"
echo "COMMIT: $PROMOTION_COMMIT"
