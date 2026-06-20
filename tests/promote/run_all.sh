#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
cd "$ROOT"

PASS_COUNT=0
FAIL_COUNT=0

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

cleanup_branch() {
  local run_id="$1"
  git worktree prune >/dev/null 2>&1 || true
  git branch -D "gate/$run_id" >/dev/null 2>&1 || true
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

cleanup_branch "$RUN_ID"

say "Summary"

echo "Passed: $PASS_COUNT"
echo "Failed: $FAIL_COUNT"

if [[ "$FAIL_COUNT" -ne 0 ]]; then
  exit 1
fi

echo "PROMOTION_TEST_MATRIX: PASS"
