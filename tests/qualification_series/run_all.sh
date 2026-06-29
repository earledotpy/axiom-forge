#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
cd "$ROOT"

SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX"' EXIT
git clone -q "$ROOT" "$SANDBOX"

write_result() {
  local path="$1"
  local case_name="$2"
  local status="$3"
  local revision="$4"
  local cli_version="$5"
  local model="$6"
  local scope="${7:-PASSED}"

  python - "$path" "$case_name" "$status" "$revision" "$cli_version" "$model" "$scope" <<'PY'
import json
import sys
from pathlib import Path

path, case, status, revision, cli_version, model, scope = sys.argv[1:]
model_val = None if model == "null" else model
Path(path).parent.mkdir(parents=True, exist_ok=True)
Path(path).write_text(json.dumps({
    "status": status,
    "adapter": "qualification-simulated-agent",
    "case": case,
    "run_id": f"run-{case}",
    "patch_sha256": f"patch-{case}",
    "case_spec": {
        "task": {"path": f"qualification/cases/{case}/task.md", "sha256": f"task-{case}"},
        "allowed_paths": {"path": f"qualification/cases/{case}/allowed-paths.txt", "sha256": f"scope-{case}"},
        "acceptance": {"path": f"qualification/cases/{case}/accept.sh", "sha256": f"acceptance-{case}"},
    },
    "scope": scope,
    "acceptance": "PASSED",
    "run_validation": "PASSED",
    "patch_verification": "PASSED",
    "adapter_configuration": {
        "adapter_script": "agents/qualification-simulated-agent.sh",
        "adapter_script_revision": revision,
        "cli_command": "python",
        "cli_path": "/fixture/python",
        "cli_version": cli_version,
        "selected_model": model_val,
        "relevant_configuration": {"protocol": "fixture-v1"},
    },
}, indent=2) + "\n", encoding="utf-8")
PY
}

assert_outcome() {
  local expected_status="$1"
  local expected_reason="$2"
  local adapter="$3"
  local out

  out="$(python scripts/evaluate_qualification_series.py --adapter "$adapter" --root "$SANDBOX")"
  python - "$out" "$expected_status" "$expected_reason" <<'PY'
import json
import sys

result = json.loads(sys.argv[1])
assert result["status"] == sys.argv[2], f"expected status {sys.argv[2]!r}, got {result['status']!r}"
expected_reason = None if sys.argv[3] == "" else sys.argv[3]
assert result["reason"] == expected_reason, f"expected reason {expected_reason!r}, got {result['reason']!r}"
PY
}

RD="$SANDBOX/qualification/results"

# S1: contiguous complete series qualifies
write_result "$RD/test-s1/0001-behavior.json"  behavior-change PASSED rev-1 cli-1 model-1
write_result "$RD/test-s1/0002-new.json"       new-behavior    PASSED rev-1 cli-1 model-1
write_result "$RD/test-s1/0003-edge.json"      edge-case       PASSED rev-1 cli-1 model-1

# S2: failed result resets the streak; the series still qualifies from the restart
write_result "$RD/test-s2/0001-behavior.json"   behavior-change PASSED rev-1 cli-1 model-1
write_result "$RD/test-s2/0002-behavior-f.json" behavior-change FAILED rev-1 cli-1 model-1
write_result "$RD/test-s2/0003-behavior2.json"  behavior-change PASSED rev-1 cli-1 model-1
write_result "$RD/test-s2/0004-new.json"        new-behavior    PASSED rev-1 cli-1 model-1
write_result "$RD/test-s2/0005-edge.json"       edge-case       PASSED rev-1 cli-1 model-1

# S3: missing identity resets the series
write_result "$RD/test-s3/0001-behavior.json" behavior-change PASSED rev-1 cli-1 model-1
write_result "$RD/test-s3/0002-new.json"      new-behavior    PASSED rev-1 cli-1 model-1
write_result "$RD/test-s3/0003-edge.json"     edge-case       PASSED rev-1 cli-1 null

# S4: failed scope resets the series
write_result "$RD/test-s4/0001-behavior.json" behavior-change PASSED rev-1 cli-1 model-1
write_result "$RD/test-s4/0002-new.json"      new-behavior    PASSED rev-1 cli-1 model-1
write_result "$RD/test-s4/0003-edge.json"     edge-case       PASSED rev-1 cli-1 model-1 FAILED

# S5: configuration drift invalidates the series
write_result "$RD/test-s5/0001-behavior.json" behavior-change PASSED rev-1 cli-1 model-1
write_result "$RD/test-s5/0002-new.json"      new-behavior    PASSED rev-1 cli-1 model-1
write_result "$RD/test-s5/0003-edge.json"     edge-case       PASSED rev-2 cli-1 model-1

# Commit all test results so the evaluator's clean-check passes
git -C "$SANDBOX" add qualification/results/
git -C "$SANDBOX" -c user.email=test@test.com -c user.name=Test \
  commit -q -m "add test qualification results"

assert_outcome QUALIFIED         ""                  test-s1
echo "PASS: S1_contiguous_complete_series_qualifies"

assert_outcome QUALIFIED         ""                  test-s2
echo "PASS: S2_failed_result_resets_series"

assert_outcome NOT_QUALIFIED     missing_identity    test-s3
echo "PASS: S3_missing_identity_resets_series"

assert_outcome NOT_QUALIFIED     failed_result       test-s4
echo "PASS: S4_unsafe_result_resets_series"

assert_outcome NOT_QUALIFIED     configuration_drift test-s5
echo "PASS: S5_configuration_drift_invalidates_series"

echo "QUALIFICATION_SERIES_TEST_MATRIX: PASS"
