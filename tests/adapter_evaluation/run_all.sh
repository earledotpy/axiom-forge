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

assert_series() {
  local adapter="$1"
  local expected_status="$2"
  local expected_reason="$3"
  local out

  out="$(cd "$SANDBOX" && python scripts/evaluate_qualification_series.py --adapter "$adapter")"
  python - "$out" "$expected_status" "$expected_reason" <<'PY'
import json
import sys

result = json.loads(sys.argv[1])
expected_reason = None if sys.argv[3] == "" else sys.argv[3]
assert result["status"] == sys.argv[2], result
assert result["reason"] == expected_reason, result
PY
}

write_qualification_result() {
  local adapter="$1"
  local file="$2"
  local case_name="$3"
  local status="$4"
  local revision="$5"
  local cli_version="$6"
  local model="$7"
  local scope="${8:-PASSED}"
  local acceptance="${9:-PASSED}"

  python - "$SANDBOX" "$adapter" "$file" "$case_name" "$status" "$revision" "$cli_version" "$model" "$scope" "$acceptance" <<'PY'
import json
import sys
from pathlib import Path

root, adapter, file_name, case, status, revision, cli_version, model, scope, acceptance = sys.argv[1:]
model_val = None if model == "null" else model
path = Path(root) / "qualification" / "results" / adapter / file_name
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps({
    "status": status,
    "adapter": adapter,
    "case": case,
    "run_id": f"run-{adapter}-{case}-{file_name}",
    "patch_sha256": f"patch-{adapter}-{case}-{file_name}",
    "case_spec": {
        "task": {"path": f"qualification/cases/{case}/task.md", "sha256": f"task-{case}"},
        "allowed_paths": {"path": f"qualification/cases/{case}/allowed-paths.txt", "sha256": f"scope-{case}"},
        "acceptance": {"path": f"qualification/cases/{case}/accept.sh", "sha256": f"acceptance-{case}"},
    },
    "scope": scope,
    "acceptance": acceptance,
    "run_validation": "PASSED",
    "patch_verification": "PASSED",
    "adapter_configuration": {
        "adapter_script": f"agents/{adapter}.sh",
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

(cd "$SANDBOX" && bash scripts/check_candidate_adapter_compatibility.sh manual-simulated-agent tasks/change-answer.task.md)

RESULT="$(latest_result manual-simulated-agent)"
RUN_ID="$(python - "$RESULT" <<'PY'
import json
import sys
from pathlib import Path

result = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(result["run_id"])
PY
)"

python - "$RESULT" <<'PY'
import json
import sys
from pathlib import Path

result = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert result["result_type"] == "candidate_adapter_compatibility"
assert result["status"] == "COMPATIBLE"
assert result["stage"] == "complete"
assert result["run_validation"] == "PASSED"
assert result["patch_verification"] == "PASSED"
assert result["standard_trust_decision"] == "NOT_STANDARD_TRUST"
assert result["promotion_decision"] == "NOT_PROMOTION_APPROVAL"
PY

(cd "$SANDBOX" && bash scripts/validate_run_dir.sh "runs/$RUN_ID" >/dev/null)
(cd "$SANDBOX" && bash scripts/verify_patch.sh "runs/$RUN_ID" >/dev/null)

if find "$SANDBOX/qualification/results/manual-simulated-agent" -name '*.json' -print -quit 2>/dev/null | grep -q .; then
  echo "FAIL: compatibility path wrote qualification results" >&2
  exit 1
fi

if [[ -e "$SANDBOX/runs/$RUN_ID/promotion.json" ]]; then
  echo "FAIL: compatibility path wrote promotion approval evidence" >&2
  exit 1
fi

if git -C "$SANDBOX" show-ref --verify --quiet "refs/heads/gate/$RUN_ID"; then
  echo "FAIL: compatibility path created a gate branch" >&2
  exit 1
fi

assert_series manual-simulated-agent NOT_QUALIFIED series_incomplete
echo "PASS: A1_compatibility_pass_is_not_standard_trust_or_promotion"

write_qualification_result standard-complete 0001-behavior.json behavior-change PASSED rev-1 cli-1 model-1
write_qualification_result standard-complete 0002-new.json new-behavior PASSED rev-1 cli-1 model-1
write_qualification_result standard-complete 0003-edge.json edge-case PASSED rev-1 cli-1 model-1

write_qualification_result standard-missing-identity 0001-behavior.json behavior-change PASSED rev-1 cli-1 model-1
write_qualification_result standard-missing-identity 0002-new.json new-behavior PASSED rev-1 cli-1 model-1
write_qualification_result standard-missing-identity 0003-edge.json edge-case PASSED rev-1 cli-1 null

write_qualification_result standard-unsafe-scope 0001-behavior.json behavior-change PASSED rev-1 cli-1 model-1
write_qualification_result standard-unsafe-scope 0002-new.json new-behavior PASSED rev-1 cli-1 model-1
write_qualification_result standard-unsafe-scope 0003-edge.json edge-case PASSED rev-1 cli-1 model-1 FAILED

write_qualification_result standard-failed-acceptance 0001-behavior.json behavior-change PASSED rev-1 cli-1 model-1
write_qualification_result standard-failed-acceptance 0002-new.json new-behavior PASSED rev-1 cli-1 model-1
write_qualification_result standard-failed-acceptance 0003-edge.json edge-case PASSED rev-1 cli-1 model-1 PASSED FAILED

write_qualification_result standard-configuration-drift 0001-behavior.json behavior-change PASSED rev-1 cli-1 model-1
write_qualification_result standard-configuration-drift 0002-new.json new-behavior PASSED rev-1 cli-1 model-1
write_qualification_result standard-configuration-drift 0003-edge.json edge-case PASSED rev-2 cli-1 model-1

git -C "$SANDBOX" add qualification/results/
git -C "$SANDBOX" -c user.email=test@test.com -c user.name=Test \
  commit -q -m "add adapter evaluation regression results"

assert_series standard-complete QUALIFIED ""
assert_series standard-missing-identity NOT_QUALIFIED missing_identity
assert_series standard-unsafe-scope NOT_QUALIFIED failed_result
assert_series standard-failed-acceptance NOT_QUALIFIED failed_result
assert_series standard-configuration-drift NOT_QUALIFIED configuration_drift
echo "PASS: A2_standard_qualification_remains_stronger_than_compatibility"

echo "ADAPTER_EVALUATION_TEST_MATRIX: PASS"
