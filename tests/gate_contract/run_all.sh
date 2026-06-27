#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "GATE_CONTRACT_TEST_MATRIX: FAIL" >&2
  echo "FAIL: not_inside_git_repo" >&2
  exit 1
}
cd "$ROOT"

PASS_COUNT=0
FAIL_COUNT=0

pass() {
  echo "PASS: $1"
  PASS_COUNT=$((PASS_COUNT + 1))
}

fail() {
  echo "FAIL: $1" >&2
  FAIL_COUNT=$((FAIL_COUNT + 1))
}

PROHIBITED_PATHS=(
  "scripts/promote.sh"
  "promote.sh"
  "scripts/forge_check.sh"
  "forge_check.sh"
  "tests/gate_contract/run_all.sh"
  "gate_contract/run_all.sh"
)

assert_no_prohibited_reference() {
  local name="$1"
  local file="$2"
  local prohibited

  if [[ ! -f "$file" ]]; then
    fail "$name missing_inspection_target=$file"
    return
  fi

  for prohibited in "${PROHIBITED_PATHS[@]}"; do
    if grep -F -q -- "$prohibited" "$file"; then
      fail "$name prohibited_reference=$prohibited"
      return
    fi
  done

  pass "$name"
}

assert_no_prohibited_reference \
  "C1_verify_patch_has_no_recursive_reference" \
  "scripts/verify_patch.sh"

assert_no_prohibited_reference \
  "C2_verify_target_has_no_recursive_reference" \
  "scripts/verify_target.py"

if python - <<'PY'
from pathlib import Path

forge_check = Path("scripts/forge_check.sh").read_text(encoding="utf-8")
adapter_check = Path("scripts/check_adapters.sh").read_text(encoding="utf-8")

assert "bash scripts/check_adapters.sh" in forge_check
assert 'report_cli_adapter "codex" "codex" "required"' in adapter_check
assert 'report_cli_adapter "claude-code" "claude" "required"' in adapter_check
assert 'report_cli_adapter "antigravity" "agy" "required"' in adapter_check
assert 'report_cli_adapter "copilot" "copilot" "required"' in adapter_check
assert 'report_cli_adapter "opencode" "opencode" "required"' in adapter_check
assert 'report_cli_adapter "cursor" "cursor-agent.cmd" "required"' in adapter_check
assert 'report_cli_adapter "kiro" "kiro-cli.exe" "required"' in adapter_check
assert 'report_cli_adapter "qoder" "qodercli-1.0.30.exe" "required"' in adapter_check
assert 'report_cli_adapter "kilo" "kilo" "required"' in adapter_check
assert "required standard adapter CLI unavailable" in adapter_check
PY
then
  pass "C3_health_check_requires_standard_adapter_clis"
else
  fail "C3_health_check_requires_standard_adapter_clis"
fi

if python - "gate.toml" "${PROHIBITED_PATHS[@]}" <<'PY'
import sys
import tomllib
from pathlib import Path

config_path = Path(sys.argv[1])
prohibited = sys.argv[2:]

try:
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    required = config["verify"]["required_checks"]
    checks = config["checks"]
except Exception as exc:
    print(f"gate_config_read_error={exc}", file=sys.stderr)
    raise SystemExit(1)

for name in required:
    try:
        command = checks[name]["command"]
    except Exception as exc:
        print(f"required_check_read_error={name}: {exc}", file=sys.stderr)
        raise SystemExit(1)

    command_text = " ".join(str(part) for part in command)
    for path in prohibited:
        if path in command_text:
            print(
                f"required_check_prohibited_reference={name}:{path}",
                file=sys.stderr,
            )
            raise SystemExit(1)
PY
then
  pass "C4_required_verification_commands_have_no_recursive_reference"
else
  fail "C4_required_verification_commands_have_no_recursive_reference"
fi

if python - <<'PY'
from pathlib import Path

adapter = Path("agents/antigravity.sh").read_text(encoding="utf-8")
for required in (
    "Do not run Axiom Forge runner, qualification, promotion, or test-matrix scripts.",
    "Do not run tests/runner/run_all.sh.",
):
    assert required in adapter
PY
then
  pass "C5_antigravity_prompt_forbids_recursive_harness_execution"
else
  fail "C5_antigravity_prompt_forbids_recursive_harness_execution"
fi

if python - <<'PY'
from pathlib import Path

adapter = Path("agents/copilot.sh").read_text(encoding="utf-8")
for required in (
    "Do not run Axiom Forge runner, qualification, promotion, or test-matrix scripts.",
    "Do not run tests/runner/run_all.sh.",
):
    assert required in adapter
PY
then
  pass "C6_copilot_prompt_forbids_recursive_harness_execution"
else
  fail "C6_copilot_prompt_forbids_recursive_harness_execution"
fi

if python - <<'PY'
from pathlib import Path

adapter = Path("agents/opencode.sh").read_text(encoding="utf-8")
for required in (
    "Do not run shell commands, git commands, Axiom Forge runner, qualification, promotion, or test-matrix scripts.",
    "Do not run tests/runner/run_all.sh.",
):
    assert required in adapter
PY
then
  pass "C7_opencode_prompt_forbids_recursive_harness_execution"
else
  fail "C7_opencode_prompt_forbids_recursive_harness_execution"
fi


if python - <<'PY'
from pathlib import Path

adapter = Path("agents/cursor.sh").read_text(encoding="utf-8")
for required in (
    "Do not run shell commands, git commands, Axiom Forge runner, qualification, promotion, or test-matrix scripts.",
    "Do not run tests/runner/run_all.sh.",
):
    assert required in adapter
PY
then
  pass "C8_cursor_prompt_forbids_recursive_harness_execution"
else
  fail "C8_cursor_prompt_forbids_recursive_harness_execution"
fi

if python - <<'PY'
from pathlib import Path

adapter = Path("agents/kiro.sh").read_text(encoding="utf-8")
for required in (
    "Do not run shell commands, git commands, Axiom Forge runner, qualification, promotion, or test-matrix scripts.",
    "Do not run tests/runner/run_all.sh.",
):
    assert required in adapter
assert "--trust-all-tools" not in adapter
assert "--trust-tools=read,write" in adapter
PY
then
  pass "C9_kiro_prompt_forbids_recursive_harness_execution"
else
  fail "C9_kiro_prompt_forbids_recursive_harness_execution"
fi

if python - <<'PY'
from pathlib import Path

adapter = Path("agents/qoder.sh").read_text(encoding="utf-8")
for required in (
    "Do not run shell commands, git commands, Axiom Forge runner, qualification, promotion, or test-matrix scripts.",
    "Do not run tests/runner/run_all.sh.",
):
    assert required in adapter
assert "--dangerously-skip-permissions" not in adapter
assert "--permission-mode accept_edits" in adapter
PY
then
  pass "C10_qoder_prompt_forbids_recursive_harness_execution"
else
  fail "C10_qoder_prompt_forbids_recursive_harness_execution"
fi

if python - <<'PY'
from pathlib import Path

adapter = Path("agents/kilo.sh").read_text(encoding="utf-8")
for required in (
    "Do not run shell commands, git commands, Axiom Forge runner, qualification, promotion, or test-matrix scripts.",
    "Do not run tests/runner/run_all.sh.",
):
    assert required in adapter
assert "--dangerously-skip-permissions" not in adapter
assert "--auto" in adapter
PY
then
  pass "C11_kilo_prompt_forbids_recursive_harness_execution"
else
  fail "C11_kilo_prompt_forbids_recursive_harness_execution"
fi
if [[ "$FAIL_COUNT" -ne 0 ]]; then
  echo "GATE_CONTRACT_TEST_MATRIX: FAIL" >&2
  exit 1
fi

echo "GATE_CONTRACT_TEST_MATRIX: PASS"
