#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
cd "$ROOT"

PASS_COUNT=0
FAIL_COUNT=0
TMPDIR="$(mktemp -d)"
GATE_BACKUP="$(mktemp)"
cp gate.toml "$GATE_BACKUP"

say() {
  printf "\n== %s ==\n" "$1"
}

pass() {
  echo "PASS: $1"
  PASS_COUNT=$((PASS_COUNT + 1))
}

fail() {
  echo "FAIL: $1" >&2
  FAIL_COUNT=$((FAIL_COUNT + 1))
}

cleanup() {
  cp "$GATE_BACKUP" gate.toml
  rm -f "$GATE_BACKUP"
  rm -rf "$TMPDIR"
}
trap cleanup EXIT

cleanup_branch() {
  local run_id="$1"
  git worktree prune >/dev/null 2>&1 || true
  git branch -D "gate/$run_id" >/dev/null 2>&1 || true
}

cleanup_target_branch() {
  local repo="$1"
  local run_id="$2"
  git -C "$repo" worktree prune >/dev/null 2>&1 || true
  git -C "$repo" branch -D "gate/$run_id" >/dev/null 2>&1 || true
}

path_for_toml() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -m "$1"
  else
    printf '%s\n' "$1"
  fi
}

make_good_run() {
  local run_id="$1"
  local run_dir="runs/$run_id"
  local base_sha
  local patch_sha

  base_sha="$(git rev-parse HEAD)"

  mkdir -p "$run_dir"

  cat > "$run_dir/patch.diff" <<'PATCH'
diff --git a/app/target.py b/app/target.py
--- a/app/target.py
+++ b/app/target.py
@@ -1,2 +1,2 @@
 def answer():
-    return "base"
+    return "promoted"
PATCH

  patch_sha="$(python scripts/sha256_file.py "$run_dir/patch.diff")"

  cat > "$run_dir/record.json" <<JSON
{
  "schema_version": 1,
  "run_id": "$run_id",
  "agent": "test-agent",
  "target_repo": ".",
  "base_sha": "$base_sha",
  "patch_file": "patch.diff",
  "patch_sha256": "$patch_sha",
  "run_status": "COMPLETED"
}
JSON
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
raise SystemExit(0 if 'return "after"' in text else 1)
PY
  git -C "$repo" add app/target.py check_target.py
  git -C "$repo" commit -q -m "initial target"
}

write_target_gate_config() {
  local repo
  repo="$(path_for_toml "$1")"
  local command="${2:-python check_target.py}"

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
command = [$command]
timeout_seconds = 120

[promotion]
branch_prefix = "gate/"
patch_file = "patch.diff"
record_file = "record.json"
promotion_file = "promotion.json"
TOML
}

write_target_run() {
  local run_id="$1"
  local repo="$2"
  local base_sha
  local patch_sha
  local scope_sha
  local forge_revision

  base_sha="$(git -C "$repo" rev-parse HEAD)"
  mkdir -p "runs/$run_id"

  cat > "runs/$run_id/patch.diff" <<'PATCH'
diff --git a/app/target.py b/app/target.py
--- a/app/target.py
+++ b/app/target.py
@@ -1,2 +1,2 @@
 def answer():
-    return "before"
+    return "after"
PATCH
  patch_sha="$(python scripts/sha256_file.py "runs/$run_id/patch.diff")"
  printf 'app/target.py\n' > "runs/$run_id/allowed-paths.txt"
  scope_sha="$(python scripts/sha256_file.py "runs/$run_id/allowed-paths.txt")"
  forge_revision="$(git rev-parse HEAD)"

  python - "runs/$run_id/record.json" "$run_id" "$repo" "$base_sha" "$patch_sha" "$scope_sha" "$forge_revision" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

record_path, run_id, repo, base_sha, patch_sha, scope_sha, forge_revision = sys.argv[1:]
record = {
    "schema_version": 2,
    "run_id": run_id,
    "agent": "test-agent",
    "run_mode": "target",
    "target_repo": str(Path(repo).resolve()),
    "target_name": "test-target",
    "target_base_branch": "main",
    "target_base_sha": base_sha,
    "target_remote_url": "https://example.test/target.git",
    "target_scope_file": "allowed-paths.txt",
    "target_scope_sha256": scope_sha,
    "delegation_artifact_revision": forge_revision,
    "delegation_target_base_sha": base_sha,
    "delegation_task_file": "tasks/target-verify-fixture.task.md",
    "base_sha": base_sha,
    "task_file": "task.md",
    "patch_file": "patch.diff",
    "patch_sha256": patch_sha,
    "cli_command": "test-agent",
    "cli_path": "/bin/test-agent",
    "cli_version": "test",
    "run_status": "COMPLETED",
    "failure_reason": None,
    "timestamp_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
}
Path(record_path).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
PY
}
expect_fail() {
  local name="$1"
  shift

  if "$@" >/tmp/axiom-forge-test.out 2>/tmp/axiom-forge-test.err; then
    fail "$name"
    cat /tmp/axiom-forge-test.out
    cat /tmp/axiom-forge-test.err >&2
  else
    pass "$name"
  fi
}

expect_pass() {
  local name="$1"
  shift

  if "$@" >/tmp/axiom-forge-test.out 2>/tmp/axiom-forge-test.err; then
    pass "$name"
  else
    fail "$name"
    cat /tmp/axiom-forge-test.out
    cat /tmp/axiom-forge-test.err >&2
  fi
}

say "Preflight"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Repo must be clean before promotion tests." >&2
  git status --short >&2
  exit 1
fi

expect_pass "base unit tests pass" python -m unittest discover -s tests

say "Operator approval"

RUN_ID="test-operator-approval"
expect_pass "T0_operator_exact_run_id_passes" \
  bash -c "printf '$RUN_ID\\n' | bash scripts/require_operator_approval.sh '$RUN_ID'"
expect_pass "T0a_operator_crlf_run_id_passes" \
  bash -c "printf '$RUN_ID\\r\\n' | bash scripts/require_operator_approval.sh '$RUN_ID'"

APPROVAL_STDERR="$TMPDIR/operator-approval-mismatch.err"
if bash -c "printf 'wrong-id\\n' | bash scripts/require_operator_approval.sh '$RUN_ID'" \
  >/dev/null 2>"$APPROVAL_STDERR"; then
  fail "T0b_operator_mismatch_fails_closed"
elif grep -q "operator_confirmation_mismatch" "$APPROVAL_STDERR"; then
  pass "T0b_operator_mismatch_fails_closed"
else
  fail "T0b_operator_mismatch_reports_confirmation_reason"
  cat "$APPROVAL_STDERR" >&2
fi

say "Failure cases"

expect_fail "T1_missing_run_dir_fails" \
  bash scripts/promote.sh "runs/does-not-exist"

RUN_ID="test-missing-record"
RUN_DIR="runs/$RUN_ID"
cleanup_branch "$RUN_ID"
mkdir -p "$RUN_DIR"
echo "not empty" > "$RUN_DIR/patch.diff"
expect_fail "T2_missing_record_json_fails" \
  bash scripts/promote.sh "$RUN_DIR"

RUN_ID="test-missing-patch"
RUN_DIR="runs/$RUN_ID"
cleanup_branch "$RUN_ID"
mkdir -p "$RUN_DIR"
cat > "$RUN_DIR/record.json" <<JSON
{
  "schema_version": 1,
  "run_id": "$RUN_ID",
  "agent": "test-agent",
  "target_repo": ".",
  "base_sha": "$(git rev-parse HEAD)",
  "patch_file": "patch.diff",
  "run_status": "COMPLETED"
}
JSON
expect_fail "T3_missing_patch_fails" \
  bash scripts/promote.sh "$RUN_DIR"

RUN_ID="bad/run/id"
RUN_DIR="runs/test-invalid-run-id"
cleanup_branch "test-invalid-run-id"
mkdir -p "$RUN_DIR"
echo "not empty" > "$RUN_DIR/patch.diff"
cat > "$RUN_DIR/record.json" <<JSON
{
  "schema_version": 1,
  "run_id": "$RUN_ID",
  "agent": "test-agent",
  "target_repo": ".",
  "base_sha": "$(git rev-parse HEAD)",
  "patch_file": "patch.diff",
  "run_status": "COMPLETED"
}
JSON
expect_fail "T4_invalid_run_id_fails" \
  bash scripts/promote.sh "$RUN_DIR"

RUN_ID="test-run-id-directory"
RECORD_RUN_ID="test-run-id-record"
RUN_DIR="runs/$RUN_ID"
cleanup_branch "$RUN_ID"
cleanup_branch "$RECORD_RUN_ID"
mkdir -p "$RUN_DIR"
cat > "$RUN_DIR/patch.diff" <<'PATCH'
diff --git a/app/target.py b/app/target.py
--- a/app/target.py
+++ b/app/target.py
@@ -1,2 +1,2 @@
 def answer():
-    return "base"
+    return "mismatched-run-id"
PATCH
PATCH_SHA="$(python scripts/sha256_file.py "$RUN_DIR/patch.diff")"
cat > "$RUN_DIR/record.json" <<JSON
{
  "schema_version": 1,
  "run_id": "$RECORD_RUN_ID",
  "agent": "test-agent",
  "target_repo": ".",
  "base_sha": "$(git rev-parse HEAD)",
  "patch_file": "patch.diff",
  "patch_sha256": "$PATCH_SHA",
  "run_status": "COMPLETED"
}
JSON
expect_fail "T4a_run_id_directory_mismatch_fails_validation" \
  bash scripts/validate_run_dir.sh "$RUN_DIR"
expect_fail "T4b_run_id_directory_mismatch_fails_promotion" \
  bash scripts/promote.sh "$RUN_DIR"

if git show-ref --verify --quiet "refs/heads/gate/$RECORD_RUN_ID"; then
  fail "T4c_run_id_directory_mismatch_creates_no_gate_branch"
else
  pass "T4c_run_id_directory_mismatch_creates_no_gate_branch"
fi
cleanup_branch "$RUN_ID"
cleanup_branch "$RECORD_RUN_ID"

RUN_ID="test-bad-base"
RUN_DIR="runs/$RUN_ID"
cleanup_branch "$RUN_ID"
mkdir -p "$RUN_DIR"
echo "not empty" > "$RUN_DIR/patch.diff"
cat > "$RUN_DIR/record.json" <<JSON
{
  "schema_version": 1,
  "run_id": "$RUN_ID",
  "agent": "test-agent",
  "target_repo": ".",
  "base_sha": "0000000000000000000000000000000000000000",
  "patch_file": "patch.diff",
  "run_status": "COMPLETED"
}
JSON
expect_fail "T5_bad_base_sha_fails" \
  bash scripts/promote.sh "$RUN_DIR"

RUN_ID="test-stale-current-base"
RUN_DIR="runs/$RUN_ID"
DEFAULT_BASE="$(python scripts/toml_get.py gate.toml project.default_base)"
STALE_BASE_SHA="$(git rev-parse "$DEFAULT_BASE^")"
cleanup_branch "$RUN_ID"
mkdir -p "$RUN_DIR"
cat > "$RUN_DIR/patch.diff" <<'PATCH'
diff --git a/app/target.py b/app/target.py
--- a/app/target.py
+++ b/app/target.py
@@ -1,2 +1,2 @@
 def answer():
-    return "base"
+    return "stale-base"
PATCH
PATCH_SHA="$(python scripts/sha256_file.py "$RUN_DIR/patch.diff")"
cat > "$RUN_DIR/record.json" <<JSON
{
  "schema_version": 1,
  "run_id": "$RUN_ID",
  "agent": "test-agent",
  "target_repo": ".",
  "base_sha": "$STALE_BASE_SHA",
  "patch_file": "patch.diff",
  "patch_sha256": "$PATCH_SHA",
  "run_status": "COMPLETED"
}
JSON
expect_pass "T5a_stale_existing_base_validates" \
  bash scripts/validate_run_dir.sh "$RUN_DIR"
expect_fail "T5b_stale_current_base_fails_promotion" \
  bash scripts/promote.sh "$RUN_DIR"

if grep -q '"reason": "stale_base_sha"' "$RUN_DIR/promotion.json"; then
  pass "T5c_stale_current_base_records_failure_reason"
else
  fail "T5c_stale_current_base_records_failure_reason"
fi

if git show-ref --verify --quiet "refs/heads/gate/$RUN_ID"; then
  fail "T5d_stale_current_base_creates_no_gate_branch"
else
  pass "T5d_stale_current_base_creates_no_gate_branch"
fi
cleanup_branch "$RUN_ID"

RUN_ID="test-superseded-run"
RUN_DIR="runs/$RUN_ID"
cleanup_branch "$RUN_ID"
mkdir -p "$RUN_DIR"
cat > "$RUN_DIR/patch.diff" <<'PATCH'
diff --git a/app/target.py b/app/target.py
--- a/app/target.py
+++ b/app/target.py
@@ -1,2 +1,2 @@
 def answer():
-    return "base"
+    return "superseded"
PATCH
PATCH_SHA="$(python scripts/sha256_file.py "$RUN_DIR/patch.diff")"
cat > "$RUN_DIR/record.json" <<JSON
{
  "schema_version": 2,
  "run_id": "$RUN_ID",
  "agent": "test-agent",
  "target_repo": ".",
  "base_sha": "$(git rev-parse HEAD)",
  "patch_file": "patch.diff",
  "patch_sha256": "$PATCH_SHA",
  "run_status": "COMPLETED",
  "superseded_by_run_id": "test-superseding-run",
  "superseded_reason": "newer_delegation_target_base"
}
JSON
expect_pass "T5e_superseded_run_still_validates_as_evidence" \
  bash scripts/validate_run_dir.sh "$RUN_DIR"
expect_fail "T5f_superseded_run_fails_promotion" \
  bash scripts/promote.sh "$RUN_DIR"
if grep -q '"reason": "superseded_captured_run"' "$RUN_DIR/promotion.json"; then
  pass "T5g_superseded_run_records_failure_reason"
else
  fail "T5g_superseded_run_records_failure_reason"
fi
if git show-ref --verify --quiet "refs/heads/gate/$RUN_ID"; then
  fail "T5h_superseded_run_creates_no_gate_branch"
else
  pass "T5h_superseded_run_creates_no_gate_branch"
fi
cleanup_branch "$RUN_ID"

RUN_ID="test-patch-apply-failure"
RUN_DIR="runs/$RUN_ID"
cleanup_branch "$RUN_ID"
mkdir -p "$RUN_DIR"
cat > "$RUN_DIR/patch.diff" <<'PATCH'
diff --git a/app/target.py b/app/target.py
--- a/app/target.py
+++ b/app/target.py
@@ -99,2 +99,2 @@
-this line does not exist
+this cannot apply
PATCH
PATCH_SHA="$(python scripts/sha256_file.py "$RUN_DIR/patch.diff")"
cat > "$RUN_DIR/record.json" <<JSON
{
  "schema_version": 1,
  "run_id": "$RUN_ID",
  "agent": "test-agent",
  "target_repo": ".",
  "base_sha": "$(git rev-parse HEAD)",
  "patch_file": "patch.diff",
  "patch_sha256": "$PATCH_SHA",
  "run_status": "COMPLETED"
}
JSON
expect_fail "T6_patch_apply_failure_fails" \
  bash scripts/promote.sh "$RUN_DIR"

RUN_ID="test-whitespace-error"
RUN_DIR="runs/$RUN_ID"
cleanup_branch "$RUN_ID"
mkdir -p "$RUN_DIR"
cat > "$RUN_DIR/patch.diff" <<'PATCH'
diff --git a/app/target.py b/app/target.py
--- a/app/target.py
+++ b/app/target.py
@@ -1,2 +1,3 @@
 def answer():
-    return "base"
+    return "whitespace-error"
+    
PATCH
PATCH_SHA="$(python scripts/sha256_file.py "$RUN_DIR/patch.diff")"
cat > "$RUN_DIR/record.json" <<JSON
{
  "schema_version": 1,
  "run_id": "$RUN_ID",
  "agent": "test-agent",
  "target_repo": ".",
  "base_sha": "$(git rev-parse HEAD)",
  "patch_file": "patch.diff",
  "patch_sha256": "$PATCH_SHA",
  "run_status": "COMPLETED"
}
JSON
expect_fail "T7_whitespace_error_fails" \
  bash scripts/promote.sh "$RUN_DIR"

RUN_ID="test-operator-mismatch"
cleanup_branch "$RUN_ID"
make_good_run "$RUN_ID"
expect_fail "T8_operator_mismatch_fails" \
  bash -c "printf 'wrong-id\n' | bash scripts/promote.sh 'runs/$RUN_ID'"

RUN_ID="test-missing-review"
cleanup_branch "$RUN_ID"
make_good_run "$RUN_ID"
expect_fail "T8a_missing_promotion_review_fails" \
  bash -c "printf '$RUN_ID\n' | bash scripts/promote.sh 'runs/$RUN_ID'"
if grep -q '"reason": "missing_promotion_review_result"' "runs/$RUN_ID/promotion.json"; then
  pass "T8b_missing_promotion_review_records_failure_reason"
else
  fail "T8b_missing_promotion_review_records_failure_reason"
fi

RUN_ID="test-malformed-review"
cleanup_branch "$RUN_ID"
make_good_run "$RUN_ID"
expect_fail "T8c_malformed_promotion_review_fails" \
  bash -c "printf '$RUN_ID\n' | bash scripts/promote.sh 'runs/$RUN_ID'"
if grep -q '"reason": "malformed_promotion_review_result"' "runs/$RUN_ID/promotion.json"; then
  pass "T8d_malformed_promotion_review_records_failure_reason"
else
  fail "T8d_malformed_promotion_review_records_failure_reason"
fi

RUN_ID="test-failing-review"
cleanup_branch "$RUN_ID"
make_good_run "$RUN_ID"
expect_fail "T8e_failing_promotion_review_fails" \
  bash -c "printf '$RUN_ID\n' | bash scripts/promote.sh 'runs/$RUN_ID'"
if grep -q '"reason": "failing_promotion_review_result"' "runs/$RUN_ID/promotion.json"; then
  pass "T8f_failing_promotion_review_records_failure_reason"
else
  fail "T8f_failing_promotion_review_records_failure_reason"
fi

RUN_ID="test-unresolved-review-followups"
cleanup_branch "$RUN_ID"
make_good_run "$RUN_ID"
expect_fail "T8g_unresolved_promotion_review_followups_fail" \
  bash -c "printf '$RUN_ID\n' | bash scripts/promote.sh 'runs/$RUN_ID'"
if grep -q '"reason": "unresolved_promotion_review_followups"' "runs/$RUN_ID/promotion.json"; then
  pass "T8h_unresolved_promotion_review_followups_record_failure_reason"
else
  fail "T8h_unresolved_promotion_review_followups_record_failure_reason"
fi


RUN_ID="test-existing-branch"
cleanup_branch "$RUN_ID"
make_good_run "$RUN_ID"
git branch "gate/$RUN_ID" "$(git rev-parse HEAD)"
expect_fail "T9_existing_gate_branch_fails" \
  bash -c "printf '$RUN_ID\n' | bash scripts/promote.sh 'runs/$RUN_ID'"
cleanup_branch "$RUN_ID"

say "Success case"

RUN_ID="test-success"
cleanup_branch "$RUN_ID"
make_good_run "$RUN_ID"

expect_pass "T10_success_creates_gate_branch" \
  bash -c "printf '$RUN_ID\n' | bash scripts/promote.sh 'runs/$RUN_ID'"

if git show-ref --verify --quiet "refs/heads/gate/$RUN_ID"; then
  pass "T10_branch_exists"
else
  fail "T10_branch_exists"
fi

if grep -q '"status": "PROMOTED"' "runs/$RUN_ID/promotion.json"; then
  pass "T11_success_records_promotion_json"
else
  fail "T11_success_records_promotion_json"
fi

if grep -q '"promotion_review_revision":' "runs/$RUN_ID/promotion.json"; then
  pass "T11a_success_records_promotion_review_revision"
else
  fail "T11a_success_records_promotion_review_revision"
fi

cleanup_branch "$RUN_ID"


say "Target-mode promotion"

TARGET_REPO="$TMPDIR/target"
make_target_repo "$TARGET_REPO"
write_target_gate_config "$TARGET_REPO" '"python", "check_target.py"'
TARGET_MAIN_BEFORE="$(git -C "$TARGET_REPO" rev-parse main)"

RUN_ID="target-flag-required"
write_target_run "$RUN_ID" "$TARGET_REPO"
expect_fail "T12_target_run_requires_explicit_flag" \
  bash scripts/promote.sh "runs/$RUN_ID"
cleanup_target_branch "$TARGET_REPO" "$RUN_ID"

RUN_ID="target-operator-mismatch"
write_target_run "$RUN_ID" "$TARGET_REPO"
expect_fail "T13_target_operator_mismatch_fails" \
  bash -c "printf 'wrong-id\n' | bash scripts/promote.sh --target 'runs/$RUN_ID'"
cleanup_target_branch "$TARGET_REPO" "$RUN_ID"

RUN_ID="target-existing-branch"
write_target_run "$RUN_ID" "$TARGET_REPO"
git -C "$TARGET_REPO" branch "gate/$RUN_ID" "$TARGET_MAIN_BEFORE"
expect_fail "T14_target_existing_gate_branch_fails" \
  bash -c "printf '$RUN_ID\n' | bash scripts/promote.sh --target 'runs/$RUN_ID'"
cleanup_target_branch "$TARGET_REPO" "$RUN_ID"

RUN_ID="target-stale-base"
write_target_run "$RUN_ID" "$TARGET_REPO"
cat >> "$TARGET_REPO/app/target.py" <<'PY'

# new base commit
PY
git -C "$TARGET_REPO" add app/target.py
git -C "$TARGET_REPO" commit -q -m "advance target base"
expect_fail "T15_target_stale_base_fails" \
  bash -c "printf '$RUN_ID\n' | bash scripts/promote.sh --target 'runs/$RUN_ID'"
if grep -q '"reason": "stale_delegation_target_base"' "runs/$RUN_ID/promotion.json"; then
  pass "T15a_target_stale_base_records_failure_reason"
else
  fail "T15a_target_stale_base_records_failure_reason"
fi
if git -C "$TARGET_REPO" show-ref --verify --quiet "refs/heads/gate/$RUN_ID"; then
  fail "T15b_target_stale_base_creates_no_gate_branch"
else
  pass "T15b_target_stale_base_creates_no_gate_branch"
fi
cleanup_target_branch "$TARGET_REPO" "$RUN_ID"

TARGET_REPO="$TMPDIR/target-after-stale"
make_target_repo "$TARGET_REPO"
write_target_gate_config "$TARGET_REPO" '"python", "check_target.py"'
TARGET_MAIN_BEFORE="$(git -C "$TARGET_REPO" rev-parse main)"

RUN_ID="target-failed-verification"
write_target_gate_config "$TARGET_REPO" '"python", "-c", "raise SystemExit(7)"'
write_target_run "$RUN_ID" "$TARGET_REPO"
expect_fail "T16_target_failed_verification_fails_closed" \
  bash -c "printf '$RUN_ID\n' | bash scripts/promote.sh --target 'runs/$RUN_ID'"
if grep -q '"reason": "pre_promotion_verification_failed"' "runs/$RUN_ID/promotion.json"; then
  pass "T16a_target_failed_verification_records_failure_reason"
else
  fail "T16a_target_failed_verification_records_failure_reason"
fi
cleanup_target_branch "$TARGET_REPO" "$RUN_ID"
write_target_gate_config "$TARGET_REPO" '"python", "check_target.py"'

RUN_ID="target-success"
write_target_run "$RUN_ID" "$TARGET_REPO"
expect_pass "T17_target_success_creates_target_gate_branch" \
  bash -c "printf '$RUN_ID\n' | bash scripts/promote.sh --target 'runs/$RUN_ID'"

if git -C "$TARGET_REPO" show-ref --verify --quiet "refs/heads/gate/$RUN_ID"; then
  pass "T17a_target_branch_exists_in_target_repo"
else
  fail "T17a_target_branch_exists_in_target_repo"
fi

if git show-ref --verify --quiet "refs/heads/gate/$RUN_ID"; then
  fail "T17b_target_branch_not_created_in_forge_repo"
else
  pass "T17b_target_branch_not_created_in_forge_repo"
fi

if [[ "$(git -C "$TARGET_REPO" rev-parse main)" == "$TARGET_MAIN_BEFORE" ]]; then
  pass "T17c_target_main_unchanged"
else
  fail "T17c_target_main_unchanged"
fi

if python - "runs/$RUN_ID/promotion.json" "$TARGET_REPO" <<'PY'
import json
import sys
from pathlib import Path

record = json.load(open(sys.argv[1], encoding="utf-8"))
assert record["status"] == "PROMOTED"
assert record["target_name"] == "test-target"
assert Path(record["target_repo"]).resolve() == Path(sys.argv[2]).resolve()
assert record["target_base_branch"] == "main"
assert record["delegation_target_base_sha"]
assert record["target_remote_url"] == "https://example.test/target.git"
assert record["branch"] == "gate/target-success"
assert record["promotion_commit"]
assert record["promotion_review_revision"]
PY
then
  pass "T17d_target_success_records_target_promotion_json"
else
  fail "T17d_target_success_records_target_promotion_json"
  cat "runs/$RUN_ID/promotion.json" >&2
fi

cleanup_target_branch "$TARGET_REPO" "$RUN_ID"

say "Summary"

echo "Passed: $PASS_COUNT"
echo "Failed: $FAIL_COUNT"

if [[ "$FAIL_COUNT" -ne 0 ]]; then
  exit 1
fi

echo "PROMOTION_TEST_MATRIX: PASS"
