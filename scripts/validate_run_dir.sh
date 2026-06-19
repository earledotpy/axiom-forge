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

RUN_ID="$(python "$SCRIPT_DIR/json_get.py" "$RECORD" run_id)" || die "missing_run_id"
safe_run_id "$RUN_ID" || die "unsafe_run_id"
[[ "$RUN_ID" == "$RUN_DIR_NAME" ]] || die "run_id_directory_mismatch"

BASE_SHA="$(python "$SCRIPT_DIR/json_get.py" "$RECORD" base_sha)" || die "missing_base_sha"
RUN_STATUS="$(python "$SCRIPT_DIR/json_get.py" "$RECORD" run_status)" || die "missing_run_status"

[[ "$RUN_STATUS" == "COMPLETED" ]] || die "run_not_completed"

git cat-file -e "$BASE_SHA^{commit}" 2>/dev/null || die "base_sha_not_found"

PATCH_EXPECTED="$(python "$SCRIPT_DIR/json_get.py" "$RECORD" patch_sha256 2>/dev/null || true)"

if [[ -n "$PATCH_EXPECTED" ]]; then
  PATCH_ACTUAL="$(python "$SCRIPT_DIR/sha256_file.py" "$PATCH")" || die "patch_sha256_compute_failed"
  [[ "$PATCH_EXPECTED" == "$PATCH_ACTUAL" ]] || die "patch_sha256_mismatch"
fi

echo "VALID_RUN_DIR: $RUN_ID"
