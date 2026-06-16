#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "$SCRIPT_DIR/common.sh"

need_cmd git
need_cmd python

[[ $# -eq 1 ]] || die "usage: promote.sh <run_dir>"

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || die "not inside a git repository"
cd "$ROOT"

RUN_ARG="$1"
[[ -d "$RUN_ARG" ]] || die "missing run_dir: $RUN_ARG"

RUN_DIR="$(cd "$RUN_ARG" && pwd -P)"
CONFIG="$ROOT/gate.toml"

RUN_ID=""
BASE_SHA=""
BRANCH=""
PROMOTION_COMMIT=""
PROMOTION_FILE="$RUN_DIR/promotion.json"
VERIFY_WT=""
GATE_WT=""
BRANCH_CREATED=0
PROMOTED_OK=0

record_promotion() {
  local status="$1"
  local reason="${2:-}"

  python "$SCRIPT_DIR/write_promotion.py" \
    --file "$PROMOTION_FILE" \
    --run-id "${RUN_ID:-}" \
    --status "$status" \
    --reason "$reason" \
    --branch "${BRANCH:-}" \
    --base-sha "${BASE_SHA:-}" \
    --promotion-commit "${PROMOTION_COMMIT:-}" \
    --pre-verification "$([[ "$status" == "PROMOTED" ]] && echo PASS || true)" \
    --post-verification "$([[ "$status" == "PROMOTED" ]] && echo PASS || true)" \
    >/dev/null 2>&1 || true
}

cleanup_failed_branch() {
  if [[ -n "${VERIFY_WT:-}" && -d "$VERIFY_WT" ]]; then
    git worktree remove -f "$VERIFY_WT" >/dev/null 2>&1 || true
  fi

  if [[ -n "${GATE_WT:-}" && -d "$GATE_WT" ]]; then
    git worktree remove -f "$GATE_WT" >/dev/null 2>&1 || true
  fi

  if [[ "$BRANCH_CREATED" == "1" && "$PROMOTED_OK" != "1" && -n "${BRANCH:-}" ]]; then
    git branch -D "$BRANCH" >/dev/null 2>&1 || true
  fi
}

fail_closed() {
  local reason="$1"
  cleanup_failed_branch
  record_promotion "FAILED" "$reason"
  echo "PROMOTION FAILED CLOSED: $reason" >&2
  exit 1
}

reject_closed() {
  local reason="$1"
  cleanup_failed_branch
  record_promotion "REJECTED" "$reason"
  echo "PROMOTION REJECTED: $reason" >&2
  exit 1
}

[[ -f "$CONFIG" ]] || fail_closed "missing_gate_toml"

DEFAULT_BASE="$(python "$SCRIPT_DIR/toml_get.py" "$CONFIG" project.default_base)" || fail_closed "malformed_gate_toml"
BRANCH_PREFIX="$(python "$SCRIPT_DIR/toml_get.py" "$CONFIG" promotion.branch_prefix)" || fail_closed "malformed_gate_toml"
PATCH_FILE_NAME="$(python "$SCRIPT_DIR/toml_get.py" "$CONFIG" promotion.patch_file)" || fail_closed "malformed_gate_toml"
RECORD_FILE_NAME="$(python "$SCRIPT_DIR/toml_get.py" "$CONFIG" promotion.record_file)" || fail_closed "malformed_gate_toml"
PROMOTION_FILE_NAME="$(python "$SCRIPT_DIR/toml_get.py" "$CONFIG" promotion.promotion_file)" || fail_closed "malformed_gate_toml"
REQUIRE_CLEAN="$(python "$SCRIPT_DIR/toml_get.py" "$CONFIG" promotion.require_clean_target)" || fail_closed "malformed_gate_toml"
REQUIRE_OPERATOR="$(python "$SCRIPT_DIR/toml_get.py" "$CONFIG" promotion.require_operator_run_id)" || fail_closed "malformed_gate_toml"
ALLOW_EXISTING="$(python "$SCRIPT_DIR/toml_get.py" "$CONFIG" promotion.allow_existing_branch)" || fail_closed "malformed_gate_toml"

PROMOTION_FILE="$RUN_DIR/$PROMOTION_FILE_NAME"

if [[ "$REQUIRE_CLEAN" == "true" ]]; then
  if [[ -n "$(git status --porcelain)" ]]; then
    fail_closed "target_repo_dirty"
  fi
fi

RECORD="$RUN_DIR/$RECORD_FILE_NAME"
PATCH="$RUN_DIR/$PATCH_FILE_NAME"

[[ -f "$RECORD" ]] || fail_closed "missing_record_json"
[[ -s "$PATCH" ]] || fail_closed "missing_or_empty_patch"

RUN_ID="$(python "$SCRIPT_DIR/json_get.py" "$RECORD" run_id)" || fail_closed "missing_run_id"
safe_run_id "$RUN_ID" || fail_closed "unsafe_run_id"

BASE_SHA="$(python "$SCRIPT_DIR/json_get.py" "$RECORD" base_sha)" || fail_closed "missing_base_sha"
RUN_STATUS="$(python "$SCRIPT_DIR/json_get.py" "$RECORD" run_status)" || fail_closed "missing_run_status"

[[ "$RUN_STATUS" == "COMPLETED" ]] || fail_closed "run_not_completed"

PATCH_EXPECTED="$(python "$SCRIPT_DIR/json_get.py" "$RECORD" patch_sha256 2>/dev/null || true)"
if [[ -n "$PATCH_EXPECTED" ]]; then
  PATCH_ACTUAL="$(python "$SCRIPT_DIR/sha256_file.py" "$PATCH")" || fail_closed "patch_sha256_compute_failed"
  [[ "$PATCH_EXPECTED" == "$PATCH_ACTUAL" ]] || fail_closed "patch_sha256_mismatch"
fi

git cat-file -e "$BASE_SHA^{commit}" 2>/dev/null || fail_closed "base_sha_not_found"

BRANCH="${BRANCH_PREFIX}${RUN_ID}"
git check-ref-format --branch "$BRANCH" >/dev/null 2>&1 || fail_closed "invalid_gate_branch_name"

if [[ "$ALLOW_EXISTING" != "true" ]]; then
  if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
    fail_closed "gate_branch_already_exists"
  fi
fi

VERIFY_WT="$(mktemp -d)"
rmdir "$VERIFY_WT"

git worktree add --detach "$VERIFY_WT" "$BASE_SHA" >/dev/null || fail_closed "verify_worktree_create_failed"

git -C "$VERIFY_WT" apply --check "$PATCH" || fail_closed "patch_check_failed"
git -C "$VERIFY_WT" apply "$PATCH" || fail_closed "patch_apply_failed"

python "$SCRIPT_DIR/verify_target.py" \
  --config "$CONFIG" \
  --worktree "$VERIFY_WT" \
  --out "$RUN_DIR/pre_verify.json" \
  || fail_closed "pre_promotion_verification_failed"

git worktree remove -f "$VERIFY_WT" >/dev/null 2>&1 || true
VERIFY_WT=""

if [[ "$REQUIRE_OPERATOR" == "true" ]]; then
  echo "Type run id to promote: $RUN_ID"
  printf "> "
  IFS= read -r TYPED_RUN_ID || fail_closed "operator_input_failed"

  if [[ "$TYPED_RUN_ID" != "$RUN_ID" ]]; then
    reject_closed "operator_confirmation_mismatch"
  fi
fi

GATE_WT="$(mktemp -d)"
rmdir "$GATE_WT"

git worktree add -b "$BRANCH" "$GATE_WT" "$BASE_SHA" >/dev/null || fail_closed "gate_worktree_create_failed"
BRANCH_CREATED=1

git -C "$GATE_WT" apply --check "$PATCH" || fail_closed "gate_patch_check_failed"
git -C "$GATE_WT" apply "$PATCH" || fail_closed "gate_patch_apply_failed"

if git -C "$GATE_WT" diff --quiet; then
  fail_closed "patch_produced_no_changes"
fi

git -C "$GATE_WT" add -A
git -C "$GATE_WT" commit \
  -m "Promote run $RUN_ID" \
  -m "Source run: $RUN_ID" \
  -m "Base SHA: $BASE_SHA" \
  >/dev/null || fail_closed "promotion_commit_failed"

PROMOTION_COMMIT="$(git -C "$GATE_WT" rev-parse HEAD)" || fail_closed "promotion_commit_lookup_failed"

python "$SCRIPT_DIR/verify_target.py" \
  --config "$CONFIG" \
  --worktree "$GATE_WT" \
  --out "$RUN_DIR/post_verify.json" \
  || fail_closed "post_promotion_verification_failed"

PROMOTED_OK=1

record_promotion "PROMOTED" ""

git worktree remove -f "$GATE_WT" >/dev/null 2>&1 || true
GATE_WT=""

echo "PROMOTED: $RUN_ID -> $BRANCH"
echo "COMMIT: $PROMOTION_COMMIT"
