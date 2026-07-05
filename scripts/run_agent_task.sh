#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "$SCRIPT_DIR/common.sh"

need_cmd git
need_cmd python

TARGET_MODE=0
if [[ $# -eq 3 && "$1" == "--target" ]]; then
  TARGET_MODE=1
  shift
fi

[[ $# -eq 2 ]] || die "usage: run_agent_task.sh [--target] <agent_name> <task_file>"

AGENT_NAME="$1"
TASK_FILE="$2"

safe_run_id "$AGENT_NAME" || die "unsafe_agent_name"

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || die "not_inside_git_repo"
cd "$ROOT"

[[ -f "$TASK_FILE" ]] || die "missing_task_file"

if [[ "$TARGET_MODE" -eq 0 && -n "$(git status --porcelain)" ]]; then
  die "target_repo_dirty"
fi

AGENT_ADAPTER="$ROOT/agents/$AGENT_NAME.sh"

RUN_ID="$(python - <<'PYID'
from datetime import datetime, timezone
print(datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f"))
PYID
)"
RUN_DIR="$ROOT/runs/$RUN_ID"
BASE_SHA=""
AGENT_WT="$ROOT/../agent-$RUN_ID"
PATCH_SHA=""
CLI_PROVENANCE_FILE="$RUN_DIR/cli-provenance.json"
CLI_COMMAND=""
CLI_PATH=""
CLI_VERSION=""
RUN_MODE="forge-local"
WORKTREE_REPO="$ROOT"
TARGET_NAME=""
TARGET_REPO="."
TARGET_BASE_BRANCH=""
TARGET_BASE_SHA=""
TARGET_REMOTE_URL=""
TARGET_PREFLIGHT_JSON="$RUN_DIR/target-preflight.json"
TARGET_PREFLIGHT_OUT="$RUN_DIR/target-preflight.out"
TARGET_SCOPE_FILE=""
TARGET_SCOPE_SHA256=""
FORGE_HEAD_BEFORE=""
FORGE_BRANCHES_BEFORE=""
FORGE_STATUS_BEFORE=""

mkdir -p "$RUN_DIR"
cp "$TASK_FILE" "$RUN_DIR/task.md"
: > "$RUN_DIR/stdout.log"
: > "$RUN_DIR/stderr.log"

write_record() {
  local status="$1"
  local reason="${2:-}"

  python "$SCRIPT_DIR/write_run_record.py" \
    --file "$RUN_DIR/record.json" \
    --run-id "$RUN_ID" \
    --agent "$AGENT_NAME" \
    --base-sha "$BASE_SHA" \
    --status "$status" \
    --task-file "task.md" \
    --patch-file "$([[ -s "$RUN_DIR/patch.diff" ]] && echo "patch.diff" || true)" \
    --patch-sha256 "$PATCH_SHA" \
    --cli-command "$CLI_COMMAND" \
    --cli-path "$CLI_PATH" \
    --cli-version "$CLI_VERSION" \
    --run-mode "$RUN_MODE" \
    --target-repo "$TARGET_REPO" \
    --target-name "$TARGET_NAME" \
    --target-base-branch "$TARGET_BASE_BRANCH" \
    --target-base-sha "$TARGET_BASE_SHA" \
    --target-remote-url "$TARGET_REMOTE_URL" \
    --target-scope-file "$TARGET_SCOPE_FILE" \
    --target-scope-sha256 "$TARGET_SCOPE_SHA256" \
    --failure-reason "$reason"
}


target_scope_sidecar_path() {
  local task_file="$1"
  [[ "$task_file" == *.task.md ]] || return 1
  printf '%s.allowed-paths.txt\n' "${task_file%.task.md}"
}

validate_and_copy_target_scope() {
  local sidecar="$1"
  local reason=""
  local status=0

  if [[ ! -e "$sidecar" ]]; then
    fail_run "missing_target_task_scope"
  fi

  set +e
  reason="$(python - "$sidecar" <<'PY'
from pathlib import Path
import sys
from scripts import target_task_scope

try:
    target_task_scope.load_scope_sidecar(Path(sys.argv[1]))
except target_task_scope.TargetTaskScopeError as exc:
    print(exc.reason)
    raise SystemExit(1)
PY
)"
  status=$?
  set -e

  if [[ "$status" -ne 0 ]]; then
    case "$reason" in
      target_scope_sidecar_missing) fail_run "missing_target_task_scope" ;;
      target_scope_empty) fail_run "empty_target_task_scope" ;;
      *) fail_run "invalid_target_task_scope" ;;
    esac
  fi

  cp "$sidecar" "$RUN_DIR/allowed-paths.txt" || fail_run "target_task_scope_copy_failed"
  [[ -s "$RUN_DIR/allowed-paths.txt" ]] || fail_run "empty_target_task_scope"
  TARGET_SCOPE_FILE="allowed-paths.txt"
  TARGET_SCOPE_SHA256="$(python "$SCRIPT_DIR/sha256_file.py" "$RUN_DIR/allowed-paths.txt")" \
    || fail_run "target_task_scope_sha256_compute_failed"
}
read_cli_provenance() {
  [[ -e "$CLI_PROVENANCE_FILE" ]] || return 0

  CLI_COMMAND="$(python "$SCRIPT_DIR/json_get.py" "$CLI_PROVENANCE_FILE" cli_command)" || return 1
  CLI_PATH="$(python "$SCRIPT_DIR/json_get.py" "$CLI_PROVENANCE_FILE" cli_path)" || return 1
  CLI_VERSION="$(python "$SCRIPT_DIR/json_get.py" "$CLI_PROVENANCE_FILE" cli_version)" || return 1
  [[ -n "$CLI_COMMAND" && -n "$CLI_PATH" ]] || return 1
}

cleanup() {
  if [[ -d "$AGENT_WT" ]]; then
    git -C "$WORKTREE_REPO" worktree remove -f "$AGENT_WT" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

fail_run() {
  local reason="$1"
  echo "RUN_FAILED: $RUN_ID" >&2
  echo "REASON: $reason" >&2
  write_record "FAILED" "$reason" || true
  exit 1
}

if [[ "$TARGET_MODE" -eq 1 ]]; then
  RUN_MODE="target"
  TARGET_REPO=""
  if [[ -n "$(git status --porcelain)" ]]; then
    fail_run "forge_repo_dirty"
  fi

  TARGET_SCOPE_SOURCE="$(target_scope_sidecar_path "$TASK_FILE")" \
    || fail_run "invalid_target_task_scope"
  validate_and_copy_target_scope "$TARGET_SCOPE_SOURCE"

  if python "$SCRIPT_DIR/target_preflight.py" \
    --config "$ROOT/gate.toml" \
    --forge-root "$ROOT" \
    --json-output "$TARGET_PREFLIGHT_JSON" \
    >"$TARGET_PREFLIGHT_OUT" 2>>"$RUN_DIR/stderr.log"; then
    cat "$TARGET_PREFLIGHT_OUT" >>"$RUN_DIR/stdout.log"
  else
    cat "$TARGET_PREFLIGHT_OUT" >>"$RUN_DIR/stdout.log"
    PREFLIGHT_REASON="$(sed -n 's/^Reason: //p' "$TARGET_PREFLIGHT_OUT" | tail -n 1)"
    fail_run "${PREFLIGHT_REASON:-target_preflight_failed}"
  fi

  TARGET_NAME="$(python "$SCRIPT_DIR/json_get.py" "$TARGET_PREFLIGHT_JSON" target_name)" \
    || fail_run "target_preflight_result_invalid"
  TARGET_REPO="$(python "$SCRIPT_DIR/json_get.py" "$TARGET_PREFLIGHT_JSON" target_repo)" \
    || fail_run "target_preflight_result_invalid"
  TARGET_BASE_BRANCH="$(python "$SCRIPT_DIR/json_get.py" "$TARGET_PREFLIGHT_JSON" base_branch)" \
    || fail_run "target_preflight_result_invalid"
  TARGET_BASE_SHA="$(python "$SCRIPT_DIR/json_get.py" "$TARGET_PREFLIGHT_JSON" base_sha)" \
    || fail_run "target_preflight_result_invalid"
  TARGET_REMOTE_URL="$(python "$SCRIPT_DIR/json_get.py" "$TARGET_PREFLIGHT_JSON" remote_url)" \
    || fail_run "target_preflight_result_invalid"
  BASE_SHA="$TARGET_BASE_SHA"
  WORKTREE_REPO="$TARGET_REPO"
else
  BASE_SHA="$(git rev-parse HEAD)"
fi

if [[ "$RUN_MODE" == "target" ]]; then
  FORGE_HEAD_BEFORE="$(git -C "$ROOT" rev-parse HEAD)" \
    || fail_run "forge_head_snapshot_failed"
  FORGE_BRANCHES_BEFORE="$(git -C "$ROOT" for-each-ref --format="%(refname)" refs/heads)" \
    || fail_run "forge_branch_snapshot_failed"
  FORGE_STATUS_BEFORE="$(git -C "$ROOT" status --porcelain=v1 --untracked-files=all --ignored=matching)" \
    || fail_run "forge_status_snapshot_failed"
fi

{
  echo "RUN_ID=$RUN_ID"
  echo "AGENT_NAME=$AGENT_NAME"
  echo "RUN_MODE=$RUN_MODE"
  echo "BASE_SHA=$BASE_SHA"
  echo "TASK_FILE=$TASK_FILE"
  echo "AGENT_ADAPTER=$AGENT_ADAPTER"
  if [[ "$RUN_MODE" == "target" ]]; then
    echo "TARGET_NAME=$TARGET_NAME"
    echo "TARGET_REPO=$TARGET_REPO"
    echo "TARGET_BASE_BRANCH=$TARGET_BASE_BRANCH"
    echo "TARGET_REMOTE_URL=$TARGET_REMOTE_URL"
  fi
} >> "$RUN_DIR/stdout.log"

[[ -x "$AGENT_ADAPTER" ]] || fail_run "agent_adapter_not_found"

git -C "$WORKTREE_REPO" worktree add --detach "$AGENT_WT" "$BASE_SHA" >>"$RUN_DIR/stdout.log" 2>>"$RUN_DIR/stderr.log" \
  || fail_run "agent_worktree_create_failed"

ADAPTER_START_HEAD="$(git -C "$AGENT_WT" rev-parse HEAD)" \
  || fail_run "adapter_start_head_lookup_failed"

BRANCHES_BEFORE="$(git -C "$WORKTREE_REPO" for-each-ref --format="%(refname)" refs/heads)" \
  || fail_run "adapter_branch_snapshot_failed"

TARGET_STATUS_BEFORE="$(git -C "$WORKTREE_REPO" status --porcelain=v1 --untracked-files=all --ignored=matching)" \
  || fail_run "target_repo_status_snapshot_failed"

ADAPTER_EXIT=0
PYTHONDONTWRITEBYTECODE=1 AXIOM_CLI_PROVENANCE_FILE="$CLI_PROVENANCE_FILE" "$AGENT_ADAPTER" "$RUN_DIR/task.md" "$AGENT_WT" >>"$RUN_DIR/stdout.log" 2>>"$RUN_DIR/stderr.log" \
  || ADAPTER_EXIT=$?

TARGET_STATUS_AFTER="$(git -C "$WORKTREE_REPO" status --porcelain=v1 --untracked-files=all --ignored=matching)" \
  || fail_run "target_repo_status_snapshot_failed"

if [[ "$TARGET_STATUS_BEFORE" != "$TARGET_STATUS_AFTER" ]]; then
  if [[ "$RUN_MODE" == "target" ]]; then
    fail_run "adapter_modified_target_repo"
  else
    fail_run "adapter_modified_outside_worktree"
  fi
fi

if [[ "$RUN_MODE" == "target" ]]; then
  FORGE_STATUS_AFTER="$(git -C "$ROOT" status --porcelain=v1 --untracked-files=all --ignored=matching)" \
    || fail_run "forge_status_snapshot_failed"

  if [[ "$FORGE_STATUS_BEFORE" != "$FORGE_STATUS_AFTER" ]]; then
    fail_run "adapter_modified_forge_checkout"
  fi
fi

read_cli_provenance || fail_run "cli_provenance_invalid"

if [[ "$ADAPTER_EXIT" -ne 0 ]]; then
  fail_run "agent_execution_failed"
fi

ADAPTER_END_HEAD="$(git -C "$AGENT_WT" rev-parse HEAD)" \
  || fail_run "adapter_end_head_lookup_failed"

if [[ "$ADAPTER_START_HEAD" != "$ADAPTER_END_HEAD" ]]; then
  fail_run "adapter_changed_head"
fi

if git -C "$AGENT_WT" symbolic-ref -q HEAD >/dev/null 2>&1; then
  fail_run "adapter_left_detached_head"
fi

BRANCHES_AFTER="$(git -C "$WORKTREE_REPO" for-each-ref --format="%(refname)" refs/heads)" \
  || fail_run "adapter_branch_snapshot_failed"

if [[ "$BRANCHES_BEFORE" != "$BRANCHES_AFTER" ]]; then
  fail_run "adapter_created_or_deleted_branch"
fi

if [[ "$RUN_MODE" == "target" ]]; then
  FORGE_HEAD_AFTER="$(git -C "$ROOT" rev-parse HEAD)" \
    || fail_run "forge_head_snapshot_failed"
  FORGE_BRANCHES_AFTER="$(git -C "$ROOT" for-each-ref --format="%(refname)" refs/heads)" \
    || fail_run "forge_branch_snapshot_failed"

  if [[ "$FORGE_HEAD_BEFORE" != "$FORGE_HEAD_AFTER" ]]; then
    fail_run "adapter_changed_forge_head"
  fi

  if [[ "$FORGE_BRANCHES_BEFORE" != "$FORGE_BRANCHES_AFTER" ]]; then
    fail_run "adapter_changed_forge_branches"
  fi
fi

git -C "$AGENT_WT" diff --binary > "$RUN_DIR/patch.diff" \
  || fail_run "patch_capture_failed"

if [[ ! -s "$RUN_DIR/patch.diff" ]]; then
  fail_run "agent_produced_empty_patch"
fi

PATCH_SHA="$(python "$SCRIPT_DIR/sha256_file.py" "$RUN_DIR/patch.diff")" \
  || fail_run "patch_sha256_compute_failed"

write_record "COMPLETED" ""

echo "RUN_CAPTURED: $RUN_ID"
echo "RUN_DIR: runs/$RUN_ID"
