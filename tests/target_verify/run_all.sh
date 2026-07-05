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

cleanup() {
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

write_gate_config() {
  local repo
  repo="$(path_for_toml "$1")"
  local command="${2:-python check_target.py}"

  cat > gate.toml <<TOML
[target.primary]
name = "test-target"
repo_path = "$repo"
expected_base_branch = "main"
expected_remote_url = "https://example.test/target.git"

[target.primary.verify]
command = [$command]
timeout_seconds = 120
TOML
}

write_target_run() {
  local run_id="$1"
  local repo="$2"
  local target_name="${3:-test-target}"
  local base_sha
  local patch_sha
  local scope_sha

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

  python - "runs/$run_id/record.json" "$run_id" "$repo" "$target_name" "$base_sha" "$patch_sha" "$scope_sha" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

record_path, run_id, repo, target_name, base_sha, patch_sha, scope_sha = sys.argv[1:]
record = {
    "schema_version": 2,
    "run_id": run_id,
    "agent": "test-agent",
    "run_mode": "target",
    "target_repo": str(Path(repo).resolve()),
    "target_name": target_name,
    "target_base_branch": "main",
    "target_base_sha": base_sha,
    "target_remote_url": "https://example.test/target.git",
    "target_scope_file": "allowed-paths.txt",
    "target_scope_sha256": scope_sha,
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
write_forge_local_run() {
  local run_id="$1"
  local base_sha
  local patch_sha

  base_sha="$(git rev-parse HEAD)"
  mkdir -p "runs/$run_id"
  cat > "runs/$run_id/patch.diff" <<'PATCH'
diff --git a/app/target.py b/app/target.py
--- a/app/target.py
+++ b/app/target.py
@@ -1,2 +1,2 @@
 def answer():
-    return "base"
+    return "target-flag-rejected"
PATCH
  patch_sha="$(python scripts/sha256_file.py "runs/$run_id/patch.diff")"
  cat > "runs/$run_id/record.json" <<JSON
{
  "schema_version": 2,
  "run_id": "$run_id",
  "agent": "test-agent",
  "run_mode": "forge-local",
  "target_repo": ".",
  "target_name": null,
  "target_base_branch": null,
  "target_base_sha": null,
  "target_remote_url": null,
  "base_sha": "$base_sha",
  "patch_file": "patch.diff",
  "patch_sha256": "$patch_sha",
  "run_status": "COMPLETED",
  "failure_reason": null
}
JSON
}

expect_fail_reason() {
  local name="$1"
  local reason="$2"
  shift 2

  if "$@" >/tmp/axiom-target-verify.out 2>/tmp/axiom-target-verify.err; then
    fail "$name"
    cat /tmp/axiom-target-verify.out
    return
  fi

  if grep -q "$reason" /tmp/axiom-target-verify.err /tmp/axiom-target-verify.out; then
    pass "$name"
  else
    fail "$name wrong reason"
    cat /tmp/axiom-target-verify.out
    cat /tmp/axiom-target-verify.err >&2
  fi
}

expect_pass() {
  local name="$1"
  shift

  if "$@" >/tmp/axiom-target-verify.out 2>/tmp/axiom-target-verify.err; then
    pass "$name"
  else
    fail "$name"
    cat /tmp/axiom-target-verify.out
    cat /tmp/axiom-target-verify.err >&2
  fi
}

TARGET_REPO="$TMPDIR/target"
make_target_repo "$TARGET_REPO"
write_gate_config "$TARGET_REPO" '"python", "check_target.py"'

write_target_run "target-verify-missing-scope-copy" "$TARGET_REPO"
rm -f runs/target-verify-missing-scope-copy/allowed-paths.txt
expect_fail_reason \
  "V0a_target_run_validation_requires_copied_scope_file" \
  "missing_or_empty_target_scope_file" \
  bash scripts/validate_run_dir.sh runs/target-verify-missing-scope-copy

write_target_run "target-verify-scope-hash-mismatch" "$TARGET_REPO"
printf 'app/other.py\n' > runs/target-verify-scope-hash-mismatch/allowed-paths.txt
expect_fail_reason \
  "V0b_target_run_validation_rejects_scope_hash_mismatch" \
  "target_scope_sha256_mismatch" \
  bash scripts/validate_run_dir.sh runs/target-verify-scope-hash-mismatch
write_target_run "target-verify-success" "$TARGET_REPO"
expect_fail_reason \
  "V1_target_run_requires_explicit_flag" \
  "target_mode_requires_explicit_flag" \
  bash scripts/verify_patch.sh runs/target-verify-success

write_forge_local_run "target-verify-forge-local"
expect_fail_reason \
  "V2_target_flag_rejects_forge_local_run" \
  "target_flag_requires_target_run" \
  bash scripts/verify_patch.sh --target runs/target-verify-forge-local

expect_pass \
  "V3_target_mode_verifies_with_target_owned_command" \
  bash scripts/verify_patch.sh --target runs/target-verify-success

if python - "runs/target-verify-success/verify.json" <<'PY'
import json
import sys
result = json.load(open(sys.argv[1], encoding="utf-8"))
assert result["status"] == "PASS"
assert result["check"]["command"] == ["python", "check_target.py"]
PY
then
  pass "V3a_target_success_writes_stable_verify_json"
else
  fail "V3a_target_success_writes_stable_verify_json"
  cat runs/target-verify-success/verify.json >&2
fi

write_gate_config "$TARGET_REPO" '"python", "-c", "raise SystemExit(7)"'
write_target_run "target-verify-command-fail" "$TARGET_REPO"
expect_fail_reason \
  "V4_target_command_failure_fails_closed" \
  "verification_failed" \
  bash scripts/verify_patch.sh --target runs/target-verify-command-fail

if python - "runs/target-verify-command-fail/verify.json" <<'PY'
import json
import sys
result = json.load(open(sys.argv[1], encoding="utf-8"))
assert result["status"] == "FAIL"
assert result["reason"] == "target_verification_failed"
assert result["check"]["returncode"] == 7
PY
then
  pass "V4a_target_failure_writes_stable_reason"
else
  fail "V4a_target_failure_writes_stable_reason"
  cat runs/target-verify-command-fail/verify.json >&2
fi

write_gate_config "$TARGET_REPO" '"python", "check_target.py"'
write_target_run "target-verify-name-mismatch" "$TARGET_REPO" "other-target"
expect_fail_reason \
  "V5_target_identity_mismatch_fails" \
  "target_name_mismatch" \
  bash scripts/verify_patch.sh --target runs/target-verify-name-mismatch


write_target_run "target-verify-stale-base" "$TARGET_REPO"
python - "runs/target-verify-stale-base/record.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
record = json.loads(path.read_text(encoding="utf-8"))
record["base_sha"] = "0000000000000000000000000000000000000000"
record["target_base_sha"] = "0000000000000000000000000000000000000000"
path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
PY
expect_fail_reason \
  "V5a_stale_target_base_fails" \
  "target_base_sha_not_found" \
  bash scripts/verify_patch.sh --target runs/target-verify-stale-base

write_target_run "target-verify-cleanup" "$TARGET_REPO"
BEFORE_WORKTREES="$(git -C "$TARGET_REPO" worktree list --porcelain)"
expect_pass \
  "V6_target_verifier_worktree_cleans_up" \
  bash scripts/verify_patch.sh --target runs/target-verify-cleanup
AFTER_WORKTREES="$(git -C "$TARGET_REPO" worktree list --porcelain)"
if [[ "$BEFORE_WORKTREES" == "$AFTER_WORKTREES" ]]; then
  pass "V6a_target_worktree_list_restored"
else
  fail "V6a_target_worktree_list_restored"
  printf '%s\n' "$BEFORE_WORKTREES" >&2
  printf '%s\n' "$AFTER_WORKTREES" >&2
fi

echo "TARGET_VERIFY_TEST_MATRIX: PASS_COUNT=$PASS_COUNT FAIL_COUNT=$FAIL_COUNT"

if [[ "$FAIL_COUNT" -ne 0 ]]; then
  exit 1
fi

echo "TARGET_VERIFY_TEST_MATRIX: PASS"
