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
RUN_MODE="$(python - "$RECORD" <<'PY'
import json
import sys
record = json.load(open(sys.argv[1], encoding="utf-8"))
print(record.get("run_mode", "forge-local"))
PY
)" || die "invalid_run_mode"

if [[ "$RUN_MODE" == "target" ]]; then
  TARGET_REPO="$(python "$SCRIPT_DIR/json_get.py" "$RECORD" target_repo)" || die "missing_target_repo"
  git -C "$TARGET_REPO" cat-file -e "$BASE_SHA^{commit}" 2>/dev/null || die "target_base_sha_not_found"
else
  git cat-file -e "$BASE_SHA^{commit}" 2>/dev/null || die "base_sha_not_found"
fi

echo "VALID_RUN_DIR: $RUN_ID"
