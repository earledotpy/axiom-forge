#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "$SCRIPT_DIR/common.sh"

need_cmd git
need_cmd python

[[ $# -eq 2 ]] || die "usage: check_candidate_adapter_compatibility.sh <adapter-name> <task-file>"

ADAPTER="$1"
TASK_FILE="$2"
safe_run_id "$ADAPTER" || die "unsafe_adapter_name"

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || die "not_inside_git_repo"
cd "$ROOT"

[[ -f "$TASK_FILE" ]] || die "missing_task_file"

RUN_ID=""
RUN_DIR=""
COMPAT_RESULT_FILE=""
ADAPTER_SCRIPT_REVISION=""
ADAPTER_CONFIGURATION="$ROOT/qualification/adapters/$ADAPTER.json"
[[ -f "$ADAPTER_CONFIGURATION" ]] || ADAPTER_CONFIGURATION=""

write_result() {
  local status="$1"
  local stage="$2"
  local reason="$3"
  local run_validation="$4"
  local patch_verification="$5"

  python "$SCRIPT_DIR/write_compatibility_result.py" \
    --file "$COMPAT_RESULT_FILE" \
    --status "$status" \
    --stage "$stage" \
    --failure-reason "$reason" \
    --adapter "$ADAPTER" \
    --task-file "$TASK_FILE" \
    --task-source "$ROOT/$TASK_FILE" \
    --record "$RUN_DIR/record.json" \
    --adapter-script "agents/$ADAPTER.sh" \
    --adapter-script-revision "$ADAPTER_SCRIPT_REVISION" \
    --adapter-configuration "$ADAPTER_CONFIGURATION" \
    --run-validation "$run_validation" \
    --patch-verification "$patch_verification"
}

CAPTURE_STATUS=0
CAPTURE_OUTPUT=""
if CAPTURE_OUTPUT="$(bash "$SCRIPT_DIR/run_agent_task.sh" "$ADAPTER" "$TASK_FILE" 2>&1)"; then
  :
else
  CAPTURE_STATUS=$?
fi
printf '%s\n' "$CAPTURE_OUTPUT"

RUN_ID="$(printf '%s\n' "$CAPTURE_OUTPUT" | sed -nE 's/^RUN_(CAPTURED|FAILED): ([A-Za-z0-9_-]+)$/\2/p' | tail -n 1)"
[[ -n "$RUN_ID" ]] || die "compatibility_run_id_not_found"
RUN_DIR="$ROOT/runs/$RUN_ID"
COMPAT_RESULT_FILE="$ROOT/compatibility/results/$ADAPTER/$RUN_ID.json"
ADAPTER_SCRIPT_REVISION="$(git rev-parse "HEAD:agents/$ADAPTER.sh" 2>/dev/null || true)"

if [[ "$CAPTURE_STATUS" -ne 0 ]]; then
  RUN_FAILURE_VARS="$(python "$SCRIPT_DIR/json_shell_vars.py" extract --file "$RUN_DIR/record.json" failure_reason 2>/dev/null || true)"
  if [[ -n "$RUN_FAILURE_VARS" ]]; then
    eval "$RUN_FAILURE_VARS"
    RUN_FAILURE_REASON="$failure_reason"
  else
    RUN_FAILURE_REASON=""
  fi
  [[ -n "$RUN_FAILURE_REASON" ]] || RUN_FAILURE_REASON="run_capture_failed"
  write_result "INCOMPATIBLE" "run_capture" "$RUN_FAILURE_REASON" "NOT_RUN" "NOT_RUN"
  echo "COMPATIBILITY: FAIL $RUN_ID"
  echo "REASON: $RUN_FAILURE_REASON"
  exit 1
fi

if ! bash "$SCRIPT_DIR/validate_run_dir.sh" "runs/$RUN_ID" >/dev/null; then
  write_result "INCOMPATIBLE" "run_validation" "run_validation_failed" "FAILED" "NOT_RUN"
  echo "COMPATIBILITY: FAIL $RUN_ID"
  echo "REASON: run_validation_failed"
  exit 1
fi

if ! bash "$SCRIPT_DIR/verify_patch.sh" "runs/$RUN_ID" >/dev/null; then
  write_result "INCOMPATIBLE" "patch_verification" "patch_verification_failed" "PASSED" "FAILED"
  echo "COMPATIBILITY: FAIL $RUN_ID"
  echo "REASON: patch_verification_failed"
  exit 1
fi

write_result "COMPATIBLE" "complete" "" "PASSED" "PASSED"
echo "COMPATIBILITY: PASS $RUN_ID"
echo "RESULT: compatibility/results/$ADAPTER/$RUN_ID.json"
