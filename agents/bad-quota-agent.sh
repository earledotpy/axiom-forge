#!/usr/bin/env bash
set -Eeuo pipefail

[[ $# -eq 2 ]] || exit 2
[[ -n "${AXIOM_ADAPTER_FAILURE_FILE:-}" ]] || exit 2

printf '{\n  "failure_reason": "adapter_quota_exhausted"\n}\n' > "$AXIOM_ADAPTER_FAILURE_FILE"
exit 1
