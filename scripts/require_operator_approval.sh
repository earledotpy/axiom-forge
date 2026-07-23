#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "$SCRIPT_DIR/common.sh"

[[ $# -eq 1 ]] || die "usage: require_operator_approval.sh <run_id>"

RUN_ID="$1"
safe_run_id "$RUN_ID" || die "unsafe_run_id"

echo "Promotion requires explicit operator approval."
echo "Type the exact run id to continue:"
echo "$RUN_ID"
printf "> "

IFS= read -r TYPED_RUN_ID || die "operator_input_failed"
TYPED_RUN_ID="${TYPED_RUN_ID%$'\r'}"

if [[ "$TYPED_RUN_ID" != "$RUN_ID" ]]; then
  die "operator_confirmation_mismatch"
fi

echo "OPERATOR_APPROVAL: PASS $RUN_ID"
