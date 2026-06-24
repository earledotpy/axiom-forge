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
assert result["case_spec"]["task"]["sha256"]
assert result["case_spec"]["allowed_paths"]["sha256"]
assert result["case_spec"]["acceptance"]["sha256"]
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

(cd "$SANDBOX" && bash scripts/qualify_adapter.sh qualification-edge-case-agent edge-case)

RESULT="$(find "$SANDBOX/runs" -mindepth 2 -maxdepth 2 -path '*/qualification.json' -printf '%T@ %p\n' | sort -n | tail -n 1 | cut -d' ' -f2-)"

python - "$RESULT" <<'PY'
import json
import sys
from pathlib import Path

result = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert result["status"] == "PASSED"
assert result["case"] == "edge-case"
assert result["acceptance"] == "PASSED"
PY

echo "PASS: Q3_edge_case_qualification_succeeds"

expect_failure() {
  local name="$1"
  local adapter="$2"
  local case="$3"
  local expected_reason="$4"
  local result

  if (cd "$SANDBOX" && bash scripts/qualify_adapter.sh "$adapter" "$case"); then
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
  behavior-change \
  patch_outside_qualification_scope
expect_failure \
  "Q3_failed_external_acceptance_fails" \
  qualification-bad-acceptance-agent \
  behavior-change \
  acceptance_failed
expect_failure \
  "Q4_missing_identity_fails" \
  qualification-missing-identity-agent \
  behavior-change \
  adapter_configuration_incomplete
expect_failure \
  "Q5_new_behavior_out_of_scope_patch_fails" \
  qualification-outside-scope-agent \
  new-behavior \
  patch_outside_qualification_scope
expect_failure \
  "Q6_new_behavior_failed_acceptance_fails" \
  qualification-bad-acceptance-agent \
  new-behavior \
  acceptance_failed
expect_failure \
  "Q7_edge_case_out_of_scope_patch_fails" \
  qualification-outside-scope-agent \
  edge-case \
  patch_outside_qualification_scope
expect_failure \
  "Q8_edge_case_failed_acceptance_fails" \
  qualification-bad-acceptance-agent \
  edge-case \
  acceptance_failed

echo "QUALIFICATION_TEST_MATRIX: PASS"
