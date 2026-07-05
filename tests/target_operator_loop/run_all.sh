#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
cd "$ROOT"

PASS_COUNT=0
FAIL_COUNT=0
TMPDIR="$(mktemp -d)"
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

hide_gate_config_change() {
  git update-index --skip-worktree gate.toml
}

cleanup() {
  git update-index --no-skip-worktree gate.toml >/dev/null 2>&1 || true
  cp "$GATE_BACKUP" gate.toml
  rm -f "$GATE_BACKUP"
  rm -rf "$TMPDIR"
}
trap cleanup EXIT

path_for_toml() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -m "$1"
  else
    printf '%s\n' "$1"
  fi
}

expect_pass() {
  local name="$1"
  shift

  if "$@" >/tmp/axiom-target-loop.out 2>/tmp/axiom-target-loop.err; then
    pass "$name"
  else
    fail "$name"
    cat /tmp/axiom-target-loop.out
    cat /tmp/axiom-target-loop.err >&2
  fi
}

make_target_repo() {
  local repo="$1"

  git init -q -b main "$repo"
  git -C "$repo" config user.email "test@example.invalid"
  git -C "$repo" config user.name "Axiom Test"
  git -C "$repo" remote add origin "https://example.test/target.git"
  mkdir -p "$repo/app"
  cat > "$repo/app/target.py" <<'PY'
def answer():
    return "before"
PY
  cat > "$repo/check_target.py" <<'PY'
from pathlib import Path

text = Path("app/target.py").read_text(encoding="utf-8")
raise SystemExit(0 if 'return "runner-promoted"' in text else 1)
PY
  git -C "$repo" add app/target.py check_target.py
  git -C "$repo" commit -q -m "initial target"
}

write_target_gate_config() {
  local repo
  repo="$(path_for_toml "$1")"

  cat > gate.toml <<TOML
[project]
name = "axiom-forge"
default_base = "main"

[target.primary]
name = "test-target"
repo_path = "$repo"
expected_base_branch = "main"
expected_remote_url = "https://example.test/target.git"

[target.primary.verify]
command = ["python", "check_target.py"]
timeout_seconds = 120

[promotion]
branch_prefix = "gate/"
patch_file = "patch.diff"
record_file = "record.json"
promotion_file = "promotion.json"
TOML
}

echo "== Target Operator Loop Preflight =="

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Repo must be clean before target operator loop tests." >&2
  git status --short >&2
  exit 1
fi

TARGET_REPO="$TMPDIR/target"
make_target_repo "$TARGET_REPO"
write_target_gate_config "$TARGET_REPO"
hide_gate_config_change
TARGET_MAIN_BEFORE="$(git -C "$TARGET_REPO" rev-parse main)"

expect_pass \
  "L1_standalone_target_preflight_passes" \
  python scripts/target_preflight.py --config gate.toml --forge-root .

if bash scripts/run_agent_task.sh --target manual-simulated-agent tasks/change-answer.task.md >/tmp/axiom-target-loop-run.out 2>/tmp/axiom-target-loop-run.err; then
  RUN_ID="$(sed -n 's/^RUN_CAPTURED: //p' /tmp/axiom-target-loop-run.out | tail -n 1)"
  if [[ -n "$RUN_ID" && -d "runs/$RUN_ID" ]]; then
    pass "L2_target_mode_run_captures_forge_owned_evidence"
  else
    fail "L2_target_mode_run_captures_forge_owned_evidence"
    cat /tmp/axiom-target-loop-run.out
  fi
else
  fail "L2_target_mode_run_captures_forge_owned_evidence"
  cat /tmp/axiom-target-loop-run.out
  cat /tmp/axiom-target-loop-run.err >&2
  RUN_ID=""
fi

if [[ -n "${RUN_ID:-}" ]]; then
  expect_pass \
    "L3_target_run_directory_validates" \
    bash scripts/validate_run_dir.sh "runs/$RUN_ID"

  expect_pass \
    "L4_target_mode_patch_verifies" \
    bash scripts/verify_patch.sh --target "runs/$RUN_ID"

  if python - "runs/$RUN_ID/record.json" "$TARGET_REPO" "$TARGET_MAIN_BEFORE" <<'PY'
import json
import sys
from pathlib import Path

record = json.load(open(sys.argv[1], encoding="utf-8"))
target_repo = Path(sys.argv[2]).resolve()
base_sha = sys.argv[3]
assert record["run_mode"] == "target"
assert record["target_name"] == "test-target"
assert Path(record["target_repo"]).resolve() == target_repo
assert record["target_base_branch"] == "main"
assert record["target_base_sha"] == base_sha
assert record["base_sha"] == base_sha
assert record["target_scope_file"] == "allowed-paths.txt"
assert record["target_scope_sha256"]
PY
  then
    pass "L5_operator_can_inspect_target_identity_before_promotion"
  else
    fail "L5_operator_can_inspect_target_identity_before_promotion"
    cat "runs/$RUN_ID/record.json" >&2
  fi

  if [[ -s "runs/$RUN_ID/patch.diff" \
    && -s "runs/$RUN_ID/target-preflight.json" \
    && -s "runs/$RUN_ID/allowed-paths.txt" \
    && -s "runs/$RUN_ID/verify.json" \
    && ! -e "$TARGET_REPO/runs/$RUN_ID" \
    && -z "$(git -C "$TARGET_REPO" status --porcelain)" \
    && "$(git -C "$TARGET_REPO" rev-parse main)" == "$TARGET_MAIN_BEFORE" ]]; then
    pass "L6_evidence_remains_forge_owned_before_promotion"
  else
    fail "L6_evidence_remains_forge_owned_before_promotion"
    git -C "$TARGET_REPO" status --short >&2 || true
    find "$TARGET_REPO" -maxdepth 2 -type d -name runs -print >&2 || true
  fi

  expect_pass \
    "L7_target_promotion_succeeds_with_explicit_flag" \
    bash -c "printf '$RUN_ID\n' | bash scripts/promote.sh --target 'runs/$RUN_ID'"

  if git -C "$TARGET_REPO" show-ref --verify --quiet "refs/heads/gate/$RUN_ID"; then
    pass "L8_gate_branch_created_in_external_target_repository"
  else
    fail "L8_gate_branch_created_in_external_target_repository"
  fi

  if git show-ref --verify --quiet "refs/heads/gate/$RUN_ID"; then
    fail "L9_gate_branch_not_created_in_forge_repository"
  else
    pass "L9_gate_branch_not_created_in_forge_repository"
  fi

  if [[ "$(git -C "$TARGET_REPO" rev-parse main)" == "$TARGET_MAIN_BEFORE" ]]; then
    pass "L10_target_main_remains_unchanged"
  else
    fail "L10_target_main_remains_unchanged"
  fi

  if python - "runs/$RUN_ID/promotion.json" "$TARGET_REPO" <<'PY'
import json
import sys
from pathlib import Path

promotion = json.load(open(sys.argv[1], encoding="utf-8"))
target_repo = Path(sys.argv[2]).resolve()
assert promotion["status"] == "PROMOTED"
assert promotion["target_name"] == "test-target"
assert Path(promotion["target_repo"]).resolve() == target_repo
assert promotion["branch"].startswith("gate/")
assert promotion["promotion_commit"]
PY
  then
    pass "L11_promotion_record_remains_forge_owned"
  else
    fail "L11_promotion_record_remains_forge_owned"
    cat "runs/$RUN_ID/promotion.json" >&2
  fi
fi

echo "== Target Operator Loop Summary =="
echo "Passed: $PASS_COUNT"
echo "Failed: $FAIL_COUNT"

if [[ "$FAIL_COUNT" -ne 0 ]]; then
  exit 1
fi

echo "TARGET_OPERATOR_LOOP_TEST_MATRIX: PASS"
