#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "$SCRIPT_DIR/common.sh"

need_cmd git
need_cmd python

[[ $# -eq 1 ]] || die "usage: validate_run_dir.sh <run_dir>"

RUN_DIR="$1"
[[ -d "$RUN_DIR" ]] || die "missing_run_dir"
RUN_DIR_NAME="$(basename -- "$RUN_DIR")"

RECORD="$RUN_DIR/record.json"
PATCH="$RUN_DIR/patch.diff"

[[ -f "$RECORD" ]] || die "missing_record_json"
[[ -s "$PATCH" ]] || die "missing_or_empty_patch"

PATCH_ACTUAL="$(python "$SCRIPT_DIR/sha256_file.py" "$PATCH")" || die "patch_sha256_compute_failed"

RUN_RECORD_REASON="$(
  python "$SCRIPT_DIR/run_record.py" validate-completed \
    --record "$RECORD" \
    --run-dir-name "$RUN_DIR_NAME" \
    --patch-sha256-actual "$PATCH_ACTUAL"
)" || die "$RUN_RECORD_REASON"

if ! RECORD_VARS="$(python "$SCRIPT_DIR/json_shell_vars.py" extract --file "$RECORD" \
  run_id base_sha \
  --default run_mode forge-local \
  --default target_scope_file "" \
  --default delegation_artifact_revision "" \
  --default delegation_target_base_sha "" \
  --default target_repo "")"; then
  case "$RECORD_VARS" in
    missing_json_key_run_id) die "missing_run_id" ;;
    missing_json_key_base_sha) die "missing_base_sha" ;;
    *) die "invalid_run_mode" ;;
  esac
fi
eval "$RECORD_VARS"
RUN_ID="$run_id"
BASE_SHA="$base_sha"
RUN_MODE="$run_mode"
TARGET_SCOPE_FILE="$target_scope_file"
DELEGATION_ARTIFACT_REVISION="$delegation_artifact_revision"
DELEGATION_TARGET_BASE_SHA="$delegation_target_base_sha"
TARGET_REPO="$target_repo"

if [[ "$RUN_MODE" == "target" ]]; then
  [[ -n "$TARGET_SCOPE_FILE" ]] || die "missing_target_scope_file"
  [[ "$TARGET_SCOPE_FILE" == "allowed-paths.txt" ]] || die "invalid_target_scope_file"
  TARGET_SCOPE_PATH="$RUN_DIR/$TARGET_SCOPE_FILE"
  [[ -s "$TARGET_SCOPE_PATH" ]] || die "missing_or_empty_target_scope_file"
  TARGET_SCOPE_ACTUAL="$(python "$SCRIPT_DIR/sha256_file.py" "$TARGET_SCOPE_PATH")" \
    || die "target_scope_sha256_compute_failed"

  RUN_RECORD_REASON="$(
    python "$SCRIPT_DIR/run_record.py" validate-completed \
      --record "$RECORD" \
      --run-dir-name "$RUN_DIR_NAME" \
      --patch-sha256-actual "$PATCH_ACTUAL" \
      --target-scope-sha256-actual "$TARGET_SCOPE_ACTUAL"
  )" || die "$RUN_RECORD_REASON"

  [[ -n "$DELEGATION_ARTIFACT_REVISION" ]] || die "missing_delegation_artifact_revision"
  git -C "$SCRIPT_DIR/.." cat-file -e "$DELEGATION_ARTIFACT_REVISION^{commit}" 2>/dev/null || die "delegation_artifact_revision_not_found"

  [[ -n "$DELEGATION_TARGET_BASE_SHA" ]] || die "missing_delegation_target_base_sha"
  [[ -n "$TARGET_REPO" ]] || die "missing_target_repo"
  git -C "$TARGET_REPO" cat-file -e "$DELEGATION_TARGET_BASE_SHA^{commit}" 2>/dev/null || die "target_base_sha_not_found"
else
  git cat-file -e "$BASE_SHA^{commit}" 2>/dev/null || die "base_sha_not_found"
fi

echo "VALID_RUN_DIR: $RUN_ID"
