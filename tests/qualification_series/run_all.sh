#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
cd "$ROOT"

SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX"' EXIT

write_result() {
  local name="$1"
  local case_name="$2"
  local status="$3"
  local revision="$4"
  local cli_version="$5"
  local model="$6"

  python - "$SANDBOX/$name.json" "$case_name" "$status" "$revision" "$cli_version" "$model" <<'PY'
import json
import sys
from pathlib import Path

path, case, status, revision, cli_version, model = sys.argv[1:]
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
    "scope": "PASSED",
    "acceptance": "PASSED",
    "run_validation": "PASSED",
    "patch_verification": "PASSED",
    "adapter_configuration": {
        "adapter_script": "agents/qualification-simulated-agent.sh",
        "adapter_script_revision": revision,
        "cli_command": "python",
        "cli_path": "/fixture/python",
        "cli_version": cli_version,
        "selected_model": model,
        "relevant_configuration": {"protocol": "fixture-v1"},
    },
}, indent=2) + "\n", encoding="utf-8")
PY
}

assert_outcome() {
  local expected_status="$1"
  local expected_reason="$2"
  shift 2
  local out

  out="$(python scripts/evaluate_qualification_series.py "$@")"
  python - "$out" "$expected_status" "$expected_reason" <<'PY'
import json
import sys

result = json.loads(sys.argv[1])
assert result["status"] == sys.argv[2]
assert result["reason"] == (None if sys.argv[3] == "" else sys.argv[3])
PY
}

write_result behavior behavior-change PASSED rev-1 cli-1 model-1
write_result new new-behavior PASSED rev-1 cli-1 model-1
write_result edge edge-case PASSED rev-1 cli-1 model-1
assert_outcome QUALIFIED "" "$SANDBOX/behavior.json" "$SANDBOX/new.json" "$SANDBOX/edge.json"
echo "PASS: S1_contiguous_complete_series_qualifies"

write_result failed behavior-change FAILED rev-1 cli-1 model-1
assert_outcome QUALIFIED "" "$SANDBOX/behavior.json" "$SANDBOX/failed.json" "$SANDBOX/behavior.json" "$SANDBOX/new.json" "$SANDBOX/edge.json"
echo "PASS: S2_failed_result_resets_series"

python - "$SANDBOX/edge.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
data["adapter_configuration"]["selected_model"] = None
path.write_text(json.dumps(data), encoding="utf-8")
PY
assert_outcome NOT_QUALIFIED missing_identity "$SANDBOX/behavior.json" "$SANDBOX/new.json" "$SANDBOX/edge.json"
echo "PASS: S3_missing_identity_resets_series"

write_result edge-unsafe edge-case PASSED rev-1 cli-1 model-1
python - "$SANDBOX/edge-unsafe.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
data["scope"] = "FAILED"
path.write_text(json.dumps(data), encoding="utf-8")
PY
assert_outcome NOT_QUALIFIED failed_result "$SANDBOX/behavior.json" "$SANDBOX/new.json" "$SANDBOX/edge-unsafe.json"
echo "PASS: S4_unsafe_result_resets_series"

write_result edge-drift edge-case PASSED rev-2 cli-1 model-1
assert_outcome NOT_QUALIFIED configuration_drift "$SANDBOX/behavior.json" "$SANDBOX/new.json" "$SANDBOX/edge-drift.json"
echo "PASS: S5_configuration_drift_invalidates_series"
echo "QUALIFICATION_SERIES_TEST_MATRIX: PASS"
