#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
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

latest_numeric_run() {
  find runs -mindepth 1 -maxdepth 1 -type d -name '20*' -printf '%f\n' | sort | tail -n 1
}

expect_runner_fail() {
  local name="$1"
  local expected_reason="$2"
  shift 2

  local before
  local after

  before="$(latest_numeric_run || true)"

  if "$@" >/tmp/axiom-runner-test.out 2>/tmp/axiom-runner-test.err; then
    fail "$name"
    cat /tmp/axiom-runner-test.out
    cat /tmp/axiom-runner-test.err >&2
    return
  fi

  after="$(latest_numeric_run || true)"

  if [[ -z "$after" || "$after" == "$before" ]]; then
    fail "$name did not create a failed run record"
    return
  fi

  if grep -q "\"failure_reason\": \"$expected_reason\"" "runs/$after/record.json"; then
    pass "$name"
  else
    fail "$name wrong failure reason"
    cat "runs/$after/record.json" >&2
  fi
}

expect_runner_pass() {
  local name="$1"
  shift

  local before
  local after

  before="$(latest_numeric_run || true)"

  if "$@" >/tmp/axiom-runner-test.out 2>/tmp/axiom-runner-test.err; then
    after="$(latest_numeric_run || true)"

    if [[ -z "$after" || "$after" == "$before" ]]; then
      fail "$name did not create run"
      return
    fi

    if bash scripts/validate_run_dir.sh "runs/$after" >/tmp/axiom-runner-validate.out 2>/tmp/axiom-runner-validate.err; then
      pass "$name"
      echo "$after" > /tmp/axiom-runner-last-good-run
    else
      fail "$name produced invalid run"
      cat /tmp/axiom-runner-validate.out
      cat /tmp/axiom-runner-validate.err >&2
    fi
  else
    fail "$name"
    cat /tmp/axiom-runner-test.out
    cat /tmp/axiom-runner-test.err >&2
  fi
}

echo "== Runner Preflight =="

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Repo must be clean before runner tests." >&2
  git status --short >&2
  exit 1
fi

echo "== Runner Failure Cases =="

expect_runner_fail \
  "R1_missing_adapter_records_failure" \
  "agent_adapter_not_found" \
  bash scripts/run_agent_task.sh missing-agent tasks/change-answer.task.md

expect_runner_fail \
  "R2_adapter_commit_records_failure" \
  "adapter_changed_head" \
  bash scripts/run_agent_task.sh bad-commit-agent tasks/change-answer.task.md

expect_runner_fail \
  "R3_adapter_branch_records_failure" \
  "adapter_left_detached_head" \
  bash scripts/run_agent_task.sh bad-branch-agent tasks/change-answer.task.md

expect_runner_fail \
  "R4_empty_patch_records_failure" \
  "agent_produced_empty_patch" \
  bash scripts/run_agent_task.sh bad-empty-agent tasks/change-answer.task.md

expect_runner_fail \
  "R5_bad_task_records_failure" \
  "agent_execution_failed" \
  bash scripts/run_agent_task.sh manual-simulated-agent tasks/bad-missing-value.task.md

echo "== Runner Success Case =="

expect_runner_pass \
  "R6_good_adapter_produces_valid_run" \
  bash scripts/run_agent_task.sh manual-simulated-agent tasks/change-answer.task.md

RUN_ID="$(cat /tmp/axiom-runner-last-good-run)"

if bash scripts/verify_patch.sh "runs/$RUN_ID" >/tmp/axiom-runner-verify.out 2>/tmp/axiom-runner-verify.err; then
  pass "R7_good_run_verifies"
else
  fail "R7_good_run_verifies"
  cat /tmp/axiom-runner-verify.out
  cat /tmp/axiom-runner-verify.err >&2
fi

echo "== Runner Summary =="
echo "Passed: $PASS_COUNT"
echo "Failed: $FAIL_COUNT"

if [[ "$FAIL_COUNT" -ne 0 ]]; then
  exit 1
fi

echo "RUNNER_TEST_MATRIX: PASS"
