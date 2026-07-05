#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
cd "$ROOT"

PASS_COUNT=0
FAIL_COUNT=0
PARENT_SENTINEL="$ROOT/.axiom-parent-dirty-test"
OUTSIDE_WORKTREE_SENTINEL="$ROOT/tmp/.axiom-outside-worktree-test"
FORGE_DIRTY_SENTINEL="$ROOT/.axiom-forge-dirty-test"
GATE_BACKUP="$(mktemp)"
cp gate.toml "$GATE_BACKUP"

pass() {
  echo "PASS: $1"
  PASS_COUNT=$((PASS_COUNT + 1))
}

fail() {
  echo "FAIL: $1" >&2
  FAIL_COUNT=$((FAIL_COUNT + 1))
}

cleanup_parent_sentinel() {
  rm -f "$PARENT_SENTINEL"
}

cleanup_outside_worktree_sentinel() {
  rm -f "$OUTSIDE_WORKTREE_SENTINEL"
  rmdir "$ROOT/tmp" 2>/dev/null || true
}

cleanup_forge_dirty_sentinel() {
  rm -f "$FORGE_DIRTY_SENTINEL"
}

hide_gate_config_change() {
  git update-index --skip-worktree gate.toml
}

restore_gate_config() {
  git update-index --no-skip-worktree gate.toml >/dev/null 2>&1 || true
  if [[ -f "$GATE_BACKUP" ]]; then
    cp "$GATE_BACKUP" gate.toml
    rm -f "$GATE_BACKUP"
  fi
}

trap 'cleanup_parent_sentinel; cleanup_outside_worktree_sentinel; cleanup_forge_dirty_sentinel; restore_gate_config' EXIT

latest_numeric_run() {
  [[ -d runs ]] || return 0
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

make_target_repo() {
  local repo="$1"
  local remote="${2:-https://example.test/target.git}"

  git init -q -b main "$repo"
  git -C "$repo" config user.email "test@example.invalid"
  git -C "$repo" config user.name "Axiom Test"
  git -C "$repo" remote add origin "$remote"
  mkdir -p "$repo/app"
  printf 'def answer():\n    return "before"\n' > "$repo/app/target.py"
  git -C "$repo" add app/target.py
  git -C "$repo" commit -q -m "initial target"
}

write_target_gate_config() {
  local repo="$1"
  local remote="${2:-https://example.test/target.git}"

  if command -v cygpath >/dev/null 2>&1; then
    repo="$(cygpath -m "$repo")"
  fi

  cat > gate.toml <<TOML
[target.primary]
name = "test-target"
repo_path = "$repo"
expected_base_branch = "main"
expected_remote_url = "$remote"

[target.primary.verify]
command = ["python", "-m", "unittest", "discover"]
timeout_seconds = 120
TOML
}
echo "== Runner Failure Cases =="

expect_runner_fail \
  "R1_missing_adapter_records_failure" \
  "agent_adapter_not_found" \
  bash scripts/run_agent_task.sh missing-agent tasks/change-answer.task.md

expect_runner_fail \
  "R1a_missing_cli_records_failure" \
  "agent_execution_failed" \
  bash scripts/run_agent_task.sh bad-missing-cli-agent tasks/change-answer.task.md

RUN_ID="$(latest_numeric_run)"
if python - "runs/$RUN_ID/record.json" <<'PY'
import json
import sys

record = json.load(open(sys.argv[1], encoding="utf-8"))
assert record["cli_command"] is None
assert record["cli_path"] is None
assert record["cli_version"] is None
PY
then
  pass "R1b_missing_cli_does_not_fabricate_provenance"
else
  fail "R1b_missing_cli_does_not_fabricate_provenance"
  cat "runs/$RUN_ID/record.json" >&2
fi

cleanup_parent_sentinel
expect_runner_fail \
  "R2a_parent_write_records_failure" \
  "adapter_modified_outside_worktree" \
  env "AXIOM_TEST_PARENT_ROOT=$ROOT" bash scripts/run_agent_task.sh bad-parent-dirty-agent tasks/change-answer.task.md

RUN_ID="$(latest_numeric_run)"
if grep -q '"run_status": "FAILED"' "runs/$RUN_ID/record.json"; then
  pass "R2b_parent_write_run_not_completed"
else
  fail "R2b_parent_write_run_not_completed"
  cat "runs/$RUN_ID/record.json" >&2
fi

cleanup_parent_sentinel

if [[ -n "$(git status --porcelain)" ]]; then
  fail "R2c_parent_write_sentinel_cleaned"
  git status --short >&2
else
  pass "R2c_parent_write_sentinel_cleaned"
fi

cleanup_outside_worktree_sentinel
expect_runner_fail \
  "R2d_outside_worktree_write_records_failure" \
  "adapter_modified_outside_worktree" \
  env "AXIOM_TEST_PARENT_ROOT=$ROOT" bash scripts/run_agent_task.sh bad-outside-worktree-agent tasks/change-answer.task.md

cleanup_outside_worktree_sentinel

if [[ -n "$(git status --porcelain)" ]]; then
  fail "R2e_outside_worktree_sentinel_cleaned"
  git status --short >&2
else
  pass "R2e_outside_worktree_sentinel_cleaned"
fi

expect_runner_fail \
  "R2_adapter_commit_records_failure" \
  "adapter_changed_head" \
  bash scripts/run_agent_task.sh bad-commit-agent tasks/change-answer.task.md

if bash scripts/run_agent_task.sh bad-branch-agent tasks/change-answer.task.md >/tmp/axiom-runner-test.out 2>/tmp/axiom-runner-test.err; then
  fail "R3_adapter_branch_records_failure"
else
  RUN_ID="$(latest_numeric_run)"
  if grep -q '"failure_reason": "adapter_left_detached_head"\|"failure_reason": "adapter_created_or_deleted_branch"' "runs/$RUN_ID/record.json"; then
    pass "R3_adapter_branch_records_failure"
  else
    fail "R3_adapter_branch_records_failure wrong failure reason"
    cat "runs/$RUN_ID/record.json" >&2
  fi
fi

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
GOOD_RUN_ID="$RUN_ID"

if python - "runs/$RUN_ID/record.json" <<'PY'
import json
import sys

record = json.load(open(sys.argv[1], encoding="utf-8"))
assert record["schema_version"] == 2
assert record["cli_command"] == "python"
assert record["cli_path"]
assert record["cli_version"]
PY
then
  pass "R6a_completed_run_records_cli_provenance"
else
  fail "R6a_completed_run_records_cli_provenance"
  cat "runs/$RUN_ID/record.json" >&2
fi


TARGET_TMP="$(mktemp -d)"
TARGET_REPO="$TARGET_TMP/target"
make_target_repo "$TARGET_REPO"
TARGET_BASE_SHA="$(git -C "$TARGET_REPO" rev-parse HEAD)"
write_target_gate_config "$TARGET_REPO"
hide_gate_config_change

expect_runner_fail \
  "R8i_target_mode_missing_scope_sidecar_fails_closed" \
  "missing_target_task_scope" \
  bash scripts/run_agent_task.sh --target manual-simulated-agent tasks/missing-scope-fixture.task.md

expect_runner_fail \
  "R8j_target_mode_empty_scope_sidecar_fails_closed" \
  "empty_target_task_scope" \
  bash scripts/run_agent_task.sh --target manual-simulated-agent tasks/empty-scope-fixture.task.md

expect_runner_fail \
  "R8k_target_mode_invalid_scope_sidecar_fails_closed" \
  "invalid_target_task_scope" \
  bash scripts/run_agent_task.sh --target manual-simulated-agent tasks/invalid-scope-fixture.task.md
: > "$FORGE_DIRTY_SENTINEL"
expect_runner_fail \
  "R8c_target_mode_dirty_forge_records_failed_evidence" \
  "forge_repo_dirty" \
  bash scripts/run_agent_task.sh --target manual-simulated-agent tasks/change-answer.task.md
cleanup_forge_dirty_sentinel

RUN_ID="$(latest_numeric_run)"
if python - "runs/$RUN_ID/record.json" <<'PY'
import json
import sys

record = json.load(open(sys.argv[1], encoding="utf-8"))
assert record["run_mode"] == "target"
assert record["base_sha"] == ""
assert record["target_repo"] is None
assert record["target_name"] is None
assert record["target_base_sha"] is None
PY
then
  pass "R8d_dirty_forge_record_has_no_unproven_target_identity"
else
  fail "R8d_dirty_forge_record_has_no_unproven_target_identity"
  cat "runs/$RUN_ID/record.json" >&2
fi

write_target_gate_config "$TARGET_REPO" "https://example.test/wrong.git"
hide_gate_config_change
expect_runner_fail \
  "R8e_target_preflight_failure_records_stable_reason" \
  "target_remote_mismatch" \
  bash scripts/run_agent_task.sh --target manual-simulated-agent tasks/change-answer.task.md

RUN_ID="$(latest_numeric_run)"
if python - "runs/$RUN_ID/record.json" <<'PY'
import json
import sys

record = json.load(open(sys.argv[1], encoding="utf-8"))
assert record["run_mode"] == "target"
assert record["base_sha"] == ""
assert record["target_repo"] is None
assert record["target_name"] is None
assert record["target_base_sha"] is None
PY
then
  pass "R8f_preflight_failure_record_has_no_unproven_target_identity"
else
  fail "R8f_preflight_failure_record_has_no_unproven_target_identity"
  cat "runs/$RUN_ID/record.json" >&2
fi

write_target_gate_config "$TARGET_REPO"
hide_gate_config_change
expect_runner_fail \
  "R8g_target_mode_distinguishes_forge_mutation" \
  "adapter_modified_forge_checkout" \
  env "AXIOM_TEST_PARENT_ROOT=$ROOT" bash scripts/run_agent_task.sh --target bad-parent-dirty-agent tasks/change-answer.task.md
cleanup_parent_sentinel

expect_runner_fail \
  "R8h_target_mode_distinguishes_target_mutation" \
  "adapter_modified_target_repo" \
  env "AXIOM_TEST_PARENT_ROOT=$TARGET_REPO" bash scripts/run_agent_task.sh --target bad-parent-dirty-agent tasks/change-answer.task.md
rm -f "$TARGET_REPO/.axiom-parent-dirty-test"

expect_runner_pass \
  "R8_target_mode_good_adapter_produces_valid_run" \
  bash scripts/run_agent_task.sh --target manual-simulated-agent tasks/change-answer.task.md

RUN_ID="$(cat /tmp/axiom-runner-last-good-run)"

FORGE_REVISION="$(git rev-parse HEAD)"
if python - "runs/$RUN_ID/record.json" "$TARGET_BASE_SHA" "$TARGET_REPO" "$FORGE_REVISION" <<'PY'
import json
import sys
from pathlib import Path

record = json.load(open(sys.argv[1], encoding="utf-8"))
assert record["run_mode"] == "target"
assert record["target_name"] == "test-target"
assert Path(record["target_repo"]).resolve() == Path(sys.argv[3]).resolve()
assert record["delegation_artifact_revision"] == sys.argv[4]
assert record["target_base_branch"] == "main"
assert record["target_base_sha"] == sys.argv[2]
assert record["base_sha"] == sys.argv[2]
assert record["target_scope_file"] == "allowed-paths.txt"
assert record["target_scope_sha256"]
PY
then
  pass "R8a_target_mode_records_target_identity"
else
  fail "R8a_target_mode_records_target_identity"
  cat "runs/$RUN_ID/record.json" >&2
fi

if [[ -s "runs/$RUN_ID/patch.diff" ]] \
  && [[ -s "runs/$RUN_ID/allowed-paths.txt" ]] \
  && [[ ! -e "$TARGET_REPO/runs/$RUN_ID" ]] \
  && [[ -z "$(git -C "$TARGET_REPO" status --porcelain)" ]]; then
  pass "R8b_target_mode_keeps_evidence_in_forge_and_target_clean"
else
  fail "R8b_target_mode_evidence_or_target_cleanliness"
  git -C "$TARGET_REPO" status --short >&2 || true
  find "$TARGET_REPO" -maxdepth 2 -type d -name runs -print >&2 || true
fi

rm -rf "$TARGET_TMP"
restore_gate_config
RUN_ID="$GOOD_RUN_ID"
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
