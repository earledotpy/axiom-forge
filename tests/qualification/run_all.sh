#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
cd "$ROOT"

SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX"' EXIT
git clone -q "$ROOT" "$SANDBOX"

(cd "$SANDBOX" && bash scripts/qualify_adapter.sh qualification-simulated-agent behavior-change)

RESULT="$(find "$SANDBOX/runs" -mindepth 2 -maxdepth 2 -path '*/qualification.json' -printf '%T@ %p\n' | sort -n | tail -n 1 | cut -d' ' -f2-)"

python - "$RESULT" <<'PY'
import json
import sys
from pathlib import Path

result = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert result["status"] == "PASSED"
assert result["case"] == "behavior-change"
assert result["run_validation"] == "PASSED"
assert result["patch_verification"] == "PASSED"
assert result["scope"] == "PASSED"
assert result["acceptance"] == "PASSED"
assert result["adapter_configuration"]["selected_model"]
assert result["adapter_configuration"]["cli_command"]
PY

echo "PASS: Q1_behavior_change_qualification_succeeds"

(cd "$SANDBOX" && bash scripts/qualify_adapter.sh qualification-new-behavior-agent new-behavior)

RESULT="$(find "$SANDBOX/runs" -mindepth 2 -maxdepth 2 -path '*/qualification.json' -printf '%T@ %p\n' | sort -n | tail -n 1 | cut -d' ' -f2-)"

python - "$RESULT" <<'PY'
import json
import sys
from pathlib import Path

result = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert result["status"] == "PASSED"
assert result["case"] == "new-behavior"
assert result["acceptance"] == "PASSED"
PY

echo "PASS: Q2_new_behavior_qualification_succeeds"

expect_failure() {
  local name="$1"
  local adapter="$2"
  local expected_reason="$3"
  local result

  if (cd "$SANDBOX" && bash scripts/qualify_adapter.sh "$adapter" behavior-change); then
    echo "FAIL: $name unexpectedly succeeded" >&2
    exit 1
  fi

  result="$(find "$SANDBOX/runs" -mindepth 2 -maxdepth 2 -path '*/qualification.json' -printf '%T@ %p\n' | sort -n | tail -n 1 | cut -d' ' -f2-)"
  python - "$result" "$expected_reason" <<'PY'
import json
import sys
from pathlib import Path

result = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert result["status"] == "FAILED"
assert result["failure_reason"] == sys.argv[2]
PY
  echo "PASS: $name"
}

expect_failure \
  "Q2_out_of_scope_patch_fails" \
  qualification-outside-scope-agent \
  patch_outside_qualification_scope
expect_failure \
  "Q3_failed_external_acceptance_fails" \
  qualification-bad-acceptance-agent \
  acceptance_failed
expect_failure \
  "Q4_missing_identity_fails" \
  qualification-missing-identity-agent \
  adapter_configuration_incomplete

echo "QUALIFICATION_TEST_MATRIX: PASS"
