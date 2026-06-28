#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "$SCRIPT_DIR/common.sh"

need_cmd git
need_cmd python

[[ $# -eq 2 ]] || die "usage: qualify_adapter.sh <adapter-name> <case-name>"

ADAPTER="$1"
CASE="$2"
safe_run_id "$ADAPTER" || die "unsafe_adapter_name"
safe_run_id "$CASE" || die "unsafe_case_name"

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || die "not_inside_git_repo"
cd "$ROOT"

CASE_DIR="$ROOT/qualification/cases/$CASE"
TASK_FILE="$CASE_DIR/task.md"
ALLOWED_PATHS_FILE="$CASE_DIR/allowed-paths.txt"
ACCEPTANCE_SCRIPT="$CASE_DIR/accept.sh"
ADAPTER_SCRIPT="$ROOT/agents/$ADAPTER.sh"
ADAPTER_CONFIGURATION="$ROOT/agents/$ADAPTER.qualification.json"

CASE_ERROR="$(python "$SCRIPT_DIR/qualification_case.py" validate --root "$ROOT" --case "$CASE")" || die "$CASE_ERROR"
[[ -x "$ADAPTER_SCRIPT" ]] || die "agent_adapter_not_found"

RUN_ID=""
RUN_DIR=""
VERIFY_WT=""

cleanup() {
  if [[ -n "$VERIFY_WT" && -d "$VERIFY_WT" ]]; then
    git worktree remove -f "$VERIFY_WT" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

write_result() {
  local status="$1"
  local stage="$2"
  local reason="$3"
  local run_validation="$4"
  local patch_verification="$5"
  local scope="$6"
  local acceptance="$7"

  python "$SCRIPT_DIR/write_qualification_result.py" \
    --file "$RUN_DIR/qualification.json" \
    --status "$status" \
    --stage "$stage" \
    --failure-reason "$reason" \
    --adapter "$ADAPTER" \
    --case "$CASE" \
    --task-file "qualification/cases/$CASE/task.md" \
    --task-source "$TASK_FILE" \
    --allowed-paths-file "$ALLOWED_PATHS_FILE" \
    --acceptance-script "$ACCEPTANCE_SCRIPT" \
    --record "$RUN_DIR/record.json" \
    --adapter-script "agents/$ADAPTER.sh" \
    --adapter-script-revision "${ADAPTER_SCRIPT_REVISION:-}" \
    --adapter-configuration "$ADAPTER_CONFIGURATION" \
    --run-validation "$run_validation" \
    --patch-verification "$patch_verification" \
    --scope "$scope" \
    --acceptance "$acceptance"
}

CAPTURE_OUTPUT=""
if CAPTURE_OUTPUT="$(bash "$SCRIPT_DIR/run_agent_task.sh" "$ADAPTER" "$TASK_FILE" 2>&1)"; then
  :
else
  CAPTURE_STATUS=$?
fi
printf '%s\n' "$CAPTURE_OUTPUT"

RUN_ID="$(printf '%s\n' "$CAPTURE_OUTPUT" | sed -nE 's/^RUN_(CAPTURED|FAILED): ([A-Za-z0-9_-]+)$/\2/p' | tail -n 1)"
[[ -n "$RUN_ID" ]] || die "qualification_run_id_not_found"
RUN_DIR="$ROOT/runs/$RUN_ID"

if [[ "${CAPTURE_STATUS:-0}" -ne 0 ]]; then
  write_result "FAILED" "run_capture" "run_capture_failed" "FAILED" "NOT_RUN" "NOT_RUN" "NOT_RUN"
  die "qualification_run_capture_failed"
fi

if ! bash "$SCRIPT_DIR/validate_run_dir.sh" "runs/$RUN_ID" >/dev/null; then
  write_result "FAILED" "run_validation" "run_validation_failed" "FAILED" "NOT_RUN" "NOT_RUN" "NOT_RUN"
  die "qualification_run_validation_failed"
fi

if ! bash "$SCRIPT_DIR/verify_patch.sh" "runs/$RUN_ID" >/dev/null; then
  write_result "FAILED" "patch_verification" "patch_verification_failed" "PASSED" "FAILED" "NOT_RUN" "NOT_RUN"
  die "qualification_patch_verification_failed"
fi

ADAPTER_SCRIPT_REVISION="$(git rev-parse "HEAD:agents/$ADAPTER.sh")" || {
  write_result "FAILED" "identity" "adapter_script_revision_missing" "PASSED" "PASSED" "NOT_RUN" "NOT_RUN"
  die "qualification_adapter_script_revision_missing"
}

IDENTITY_ERROR="$(
  python "$SCRIPT_DIR/adapter_identity.py" validate-qualification-inputs \
    --record "$RUN_DIR/record.json" \
    --adapter-configuration "$ADAPTER_CONFIGURATION"
)" || {
  write_result "FAILED" "identity" "$IDENTITY_ERROR" "PASSED" "PASSED" "NOT_RUN" "NOT_RUN"
  die "qualification_$IDENTITY_ERROR"
}

PATCH="$RUN_DIR/patch.diff"
while IFS=$'\t' read -r _ _ path; do
  [[ -n "$path" ]] || continue
  if ! grep -Fqx -- "$path" "$ALLOWED_PATHS_FILE"; then
    write_result "FAILED" "scope" "patch_outside_qualification_scope" "PASSED" "PASSED" "FAILED" "NOT_RUN"
    die "qualification_patch_outside_scope"
  fi
done < <(git apply --numstat "$PATCH")

BASE_SHA="$(python "$SCRIPT_DIR/json_get.py" "$RUN_DIR/record.json" base_sha)"
VERIFY_WT="$(mktemp -d)"
rmdir "$VERIFY_WT"
git worktree add --detach "$VERIFY_WT" "$BASE_SHA" >/dev/null || {
  write_result "FAILED" "acceptance" "acceptance_worktree_create_failed" "PASSED" "PASSED" "PASSED" "NOT_RUN"
  die "qualification_acceptance_worktree_create_failed"
}
git -C "$VERIFY_WT" apply --check --whitespace=error "$PATCH" || {
  write_result "FAILED" "acceptance" "acceptance_patch_check_failed" "PASSED" "PASSED" "PASSED" "NOT_RUN"
  die "qualification_acceptance_patch_check_failed"
}
git -C "$VERIFY_WT" apply --whitespace=error "$PATCH" || {
  write_result "FAILED" "acceptance" "acceptance_patch_apply_failed" "PASSED" "PASSED" "PASSED" "NOT_RUN"
  die "qualification_acceptance_patch_apply_failed"
}
if ! bash "$ACCEPTANCE_SCRIPT" "$VERIFY_WT"; then
  write_result "FAILED" "acceptance" "acceptance_failed" "PASSED" "PASSED" "PASSED" "FAILED"
  die "qualification_acceptance_failed"
fi

write_result "PASSED" "complete" "" "PASSED" "PASSED" "PASSED" "PASSED"
echo "QUALIFICATION: PASS $RUN_ID"
