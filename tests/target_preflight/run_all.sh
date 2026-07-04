#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
cd "$ROOT"

PASS_COUNT=0
FAIL_COUNT=0
TMPDIR="$(mktemp -d)"

cleanup() {
  rm -rf "$TMPDIR"
}
trap cleanup EXIT

pass() {
  echo "PASS: $1"
  PASS_COUNT=$((PASS_COUNT + 1))
}

fail() {
  echo "FAIL: $1" >&2
  FAIL_COUNT=$((FAIL_COUNT + 1))
}

run_preflight() {
  python scripts/target_preflight.py --config "$1" --forge-root "$ROOT"
}

write_config() {
  local config_path="$1"
  local repo_path="$2"
  local branch="${3:-main}"
  local remote="${4:-https://example.test/target.git}"
  local verify="${5:-present}"

  if command -v cygpath >/dev/null 2>&1; then
    repo_path="$(cygpath -m "$repo_path")"
  fi

  cat > "$config_path" <<TOML
[target.primary]
name = "test-target"
repo_path = "$repo_path"
expected_base_branch = "$branch"
expected_remote_url = "$remote"
TOML

  if [[ "$verify" == "present" ]]; then
    cat >> "$config_path" <<'TOML'

[target.primary.verify]
command = ["python", "-m", "pytest"]
timeout_seconds = 120
TOML
  fi
}

make_repo() {
  local repo="$1"
  local branch="${2:-main}"
  local remote="${3:-https://example.test/target.git}"

  git init -q -b "$branch" "$repo"
  git -C "$repo" config user.email "test@example.invalid"
  git -C "$repo" config user.name "Axiom Test"
  git -C "$repo" remote add origin "$remote"
  printf "base\n" > "$repo/README.md"
  git -C "$repo" add README.md
  git -C "$repo" commit -q -m "initial"
}

expect_pass() {
  local name="$1"
  local config_path="$2"

  if run_preflight "$config_path" >/tmp/axiom-target-preflight.out 2>/tmp/axiom-target-preflight.err; then
    if grep -q "TARGET_PREFLIGHT: PASS" /tmp/axiom-target-preflight.out; then
      pass "$name"
    else
      fail "$name missing pass sentinel"
      cat /tmp/axiom-target-preflight.out
    fi
  else
    fail "$name"
    cat /tmp/axiom-target-preflight.out
    cat /tmp/axiom-target-preflight.err >&2
  fi
}

expect_fail() {
  local name="$1"
  local reason="$2"
  local config_path="$3"

  if run_preflight "$config_path" >/tmp/axiom-target-preflight.out 2>/tmp/axiom-target-preflight.err; then
    fail "$name unexpectedly passed"
    cat /tmp/axiom-target-preflight.out
    return
  fi

  if grep -q "TARGET_PREFLIGHT: FAIL" /tmp/axiom-target-preflight.out \
    && grep -q "Reason: $reason" /tmp/axiom-target-preflight.out; then
    pass "$name"
  else
    fail "$name wrong failure reason"
    cat /tmp/axiom-target-preflight.out
    cat /tmp/axiom-target-preflight.err >&2
  fi
}

GOOD_REPO="$TMPDIR/good-target"
GOOD_CONFIG="$TMPDIR/good.toml"
make_repo "$GOOD_REPO"
write_config "$GOOD_CONFIG" "$GOOD_REPO"
expect_pass "P1_successful_preflight" "$GOOD_CONFIG"

MISSING_CONFIG="$TMPDIR/missing-target.toml"
cat > "$MISSING_CONFIG" <<'TOML'
[project]
name = "missing-target"
TOML
expect_fail "P2_missing_target_config_fails" "target_config_missing" "$MISSING_CONFIG"

MALFORMED_CONFIG="$TMPDIR/malformed.toml"
cat > "$MALFORMED_CONFIG" <<'TOML'
[target.primary]
name = "bad"
repo_path = ""
expected_base_branch = "main"
expected_remote_url = "https://example.test/target.git"
TOML
expect_fail "P3_malformed_target_config_fails" "target_config_malformed" "$MALFORMED_CONFIG"

MISSING_PATH_CONFIG="$TMPDIR/missing-path.toml"
write_config "$MISSING_PATH_CONFIG" "$TMPDIR/does-not-exist"
expect_fail "P4_missing_path_fails" "target_repo_path_missing" "$MISSING_PATH_CONFIG"

INSIDE_FORGE_CONFIG="$TMPDIR/inside-forge.toml"
write_config "$INSIDE_FORGE_CONFIG" "$ROOT"
expect_fail "P5_path_inside_forge_fails" "target_repo_inside_forge_checkout" "$INSIDE_FORGE_CONFIG"

NOT_GIT_DIR="$TMPDIR/not-git"
mkdir "$NOT_GIT_DIR"
NOT_GIT_CONFIG="$TMPDIR/not-git.toml"
write_config "$NOT_GIT_CONFIG" "$NOT_GIT_DIR"
expect_fail "P6_non_git_path_fails" "target_repo_not_git_repository" "$NOT_GIT_CONFIG"

WRONG_REMOTE_CONFIG="$TMPDIR/wrong-remote.toml"
write_config "$WRONG_REMOTE_CONFIG" "$GOOD_REPO" "main" "https://example.test/wrong.git"
expect_fail "P7_wrong_remote_fails" "target_remote_mismatch" "$WRONG_REMOTE_CONFIG"

WRONG_BRANCH_CONFIG="$TMPDIR/wrong-branch.toml"
write_config "$WRONG_BRANCH_CONFIG" "$GOOD_REPO" "develop"
expect_fail "P8_wrong_branch_fails" "target_not_on_expected_base_branch" "$WRONG_BRANCH_CONFIG"

DIRTY_REPO="$TMPDIR/dirty-target"
DIRTY_CONFIG="$TMPDIR/dirty.toml"
make_repo "$DIRTY_REPO"
printf "dirty\n" >> "$DIRTY_REPO/README.md"
write_config "$DIRTY_CONFIG" "$DIRTY_REPO"
expect_fail "P9_dirty_target_fails" "target_repo_dirty" "$DIRTY_CONFIG"

NO_VERIFY_CONFIG="$TMPDIR/no-verify.toml"
write_config "$NO_VERIFY_CONFIG" "$GOOD_REPO" "main" "https://example.test/target.git" "missing"
expect_fail "P10_missing_verification_config_fails" "target_verification_config_missing" "$NO_VERIFY_CONFIG"

echo "Passed: $PASS_COUNT"
echo "Failed: $FAIL_COUNT"

if [[ "$FAIL_COUNT" -ne 0 ]]; then
  echo "TARGET_PREFLIGHT_TEST_MATRIX: FAIL" >&2
  exit 1
fi

echo "TARGET_PREFLIGHT_TEST_MATRIX: PASS"
