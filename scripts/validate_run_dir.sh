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

RUN_ID="$(python "$SCRIPT_DIR/json_get.py" "$RECORD" run_id)" || die "missing_run_id"
BASE_SHA="$(python "$SCRIPT_DIR/json_get.py" "$RECORD" base_sha)" || die "missing_base_sha"

git cat-file -e "$BASE_SHA^{commit}" 2>/dev/null || die "base_sha_not_found"

echo "VALID_RUN_DIR: $RUN_ID"
