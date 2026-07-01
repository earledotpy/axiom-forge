#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
cd "$ROOT"

SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX"' EXIT
git clone -q "$ROOT" "$SANDBOX"

latest_result() {
  local adapter="$1"
  find "$SANDBOX/compatibility/results/$adapter" -name '*.json' -printf '%T@ %p\n' | sort -n | tail -n 1 | cut -d' ' -f2-
}

(cd "$SANDBOX" && bash scripts/check_candidate_adapter_compatibility.sh manual-simulated-agent tasks/change-answer.task.md)

RESULT="$(latest_result manual-simulated-agent)"
python - "$RESULT" <<'PY'
import json
import sys
from pathlib import Path

result = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert result["result_type"] == "candidate_adapter_compatibility"
assert result["status"] == "COMPATIBLE"
assert result["stage"] == "complete"
assert result["failure_reason"] is None
assert result["run_validation"] == "PASSED"
assert result["patch_verification"] == "PASSED"
assert result["adapter_configuration"]["cli_command"]
assert result["standard_trust_decision"] == "NOT_STANDARD_TRUST"
assert result["promotion_decision"] == "NOT_PROMOTION_APPROVAL"
PY

if find "$SANDBOX/qualification/results/manual-simulated-agent" -name '*.json' -print -quit 2>/dev/null | grep -q .; then
  echo "FAIL: compatibility path wrote qualification results" >&2
  exit 1
fi

echo "PASS: C1_candidate_compatibility_succeeds_without_qualification"

if (cd "$SANDBOX" && bash scripts/check_candidate_adapter_compatibility.sh bad-empty-agent tasks/change-answer.task.md); then
  echo "FAIL: bad-empty-agent unexpectedly passed compatibility" >&2
  exit 1
fi

RESULT="$(latest_result bad-empty-agent)"
python - "$RESULT" <<'PY'
import json
import sys
from pathlib import Path

result = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert result["result_type"] == "candidate_adapter_compatibility"
assert result["status"] == "INCOMPATIBLE"
assert result["stage"] == "run_capture"
assert result["failure_reason"] == "agent_produced_empty_patch"
assert result["run_failure_reason"] == "agent_produced_empty_patch"
assert result["run_validation"] == "NOT_RUN"
assert result["patch_verification"] == "NOT_RUN"
assert result["standard_trust_decision"] == "NOT_STANDARD_TRUST"
assert result["promotion_decision"] == "NOT_PROMOTION_APPROVAL"
PY

echo "PASS: C2_failed_compatibility_records_structured_evidence"
echo "COMPATIBILITY_TEST_MATRIX: PASS"
