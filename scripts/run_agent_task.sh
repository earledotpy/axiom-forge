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
ADAPTER_FAILURE_FILE="$RUN_DIR/adapter-failure.json"
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
DELEGATION_ARTIFACT_REVISION=""
DELEGATION_TARGET_BASE_SHA=""
DELEGATION_TASK_FILE=""
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
  local record_json=""
  local record=""

  record_json="$(python "$SCRIPT_DIR/json_shell_vars.py" build \
    --field run_id "$RUN_ID" \
    --field agent "$AGENT_NAME" \
    --field base_sha "$BASE_SHA" \
    --field status "$status" \
    --field task_file "task.md" \
    --field patch_file "$([[ -s "$RUN_DIR/patch.diff" ]] && echo "patch.diff" || true)" \
    --field patch_sha256 "$PATCH_SHA" \
    --field cli_command "$CLI_COMMAND" \
    --field cli_path "$CLI_PATH" \
    --field cli_version "$CLI_VERSION" \
    --field run_mode "$RUN_MODE" \
    --field target_repo "$TARGET_REPO" \
    --field target_name "$TARGET_NAME" \
    --field target_base_branch "$TARGET_BASE_BRANCH" \
    --field target_base_sha "$TARGET_BASE_SHA" \
    --field target_remote_url "$TARGET_REMOTE_URL" \
    --field target_scope_file "$TARGET_SCOPE_FILE" \
    --field target_scope_sha256 "$TARGET_SCOPE_SHA256" \
    --field delegation_artifact_revision "$DELEGATION_ARTIFACT_REVISION" \
    --field delegation_target_base_sha "$DELEGATION_TARGET_BASE_SHA" \
    --field delegation_task_file "$DELEGATION_TASK_FILE" \
    --field failure_reason "$reason")" || return 1

  record="$(python "$SCRIPT_DIR/run_record.py" build <<<"$record_json")" || {
    printf '%s\n' "$record"
    return 1
  }
  printf '%s\n' "$record" > "$RUN_DIR/record.json"
}


prepare_target_run_artifacts() {
  local artifact_json=""
  local status=0

  set +e
  artifact_json="$(python "$SCRIPT_DIR/delegation_artifact_set.py" prepare-target-run \
    --task-file "$TASK_FILE" \
    --run-dir "$RUN_DIR" \
    --forge-root "$ROOT" \
    --delegation-artifact-revision "$DELEGATION_ARTIFACT_REVISION")"
  status=$?
  set -e

  if [[ "$status" -ne 0 ]]; then
    fail_run "${artifact_json:-invalid_delegation_artifact_set}"
  fi

  local artifact_vars=""
  artifact_vars="$(python "$SCRIPT_DIR/json_shell_vars.py" extract --json "$artifact_json" target_scope_file target_scope_sha256 delegation_artifact_revision delegation_task_file)" || fail_run "invalid_delegation_artifact_set"
  eval "$artifact_vars"
  TARGET_SCOPE_FILE="$target_scope_file"
  TARGET_SCOPE_SHA256="$target_scope_sha256"
  DELEGATION_ARTIFACT_REVISION="$delegation_artifact_revision"
  DELEGATION_TASK_FILE="$delegation_task_file"
}

read_adapter_failure_reason() {
  [[ -e "$ADAPTER_FAILURE_FILE" ]] || return 1

  local reason=""
  local failure_vars=""
  failure_vars="$(python "$SCRIPT_DIR/json_shell_vars.py" extract --file "$ADAPTER_FAILURE_FILE" failure_reason)" || return 2
  eval "$failure_vars"
  reason="$failure_reason"
  case "$reason" in
    adapter_cli_unavailable|adapter_quota_exhausted|adapter_unavailable)
      printf '%s\n' "$reason"
      return 0
      ;;
    *)
      return 2
      ;;
  esac
}
read_cli_provenance() {
  [[ -e "$CLI_PROVENANCE_FILE" ]] || return 0

  local provenance_vars=""
  provenance_vars="$(python "$SCRIPT_DIR/json_shell_vars.py" extract --file "$CLI_PROVENANCE_FILE" cli_command cli_path cli_version)" || return 1
  eval "$provenance_vars"
  CLI_COMMAND="$cli_command"
  CLI_PATH="$cli_path"
  CLI_VERSION="$cli_version"
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

  DELEGATION_ARTIFACT_REVISION="$(git -C "$ROOT" rev-parse HEAD)" \
    || fail_run "delegation_artifact_revision_unresolved"
  prepare_target_run_artifacts

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

  PREFLIGHT_VARS="$(python "$SCRIPT_DIR/json_shell_vars.py" extract --file "$TARGET_PREFLIGHT_JSON" target_name target_repo base_branch base_sha remote_url)" || fail_run "target_preflight_result_invalid"
  eval "$PREFLIGHT_VARS"
  TARGET_NAME="$target_name"
  TARGET_REPO="$target_repo"
  TARGET_BASE_BRANCH="$base_branch"
  TARGET_BASE_SHA="$base_sha"
  DELEGATION_TARGET_BASE_SHA="$TARGET_BASE_SHA"
  TARGET_REMOTE_URL="$remote_url"
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
PYTHONDONTWRITEBYTECODE=1 AXIOM_CLI_PROVENANCE_FILE="$CLI_PROVENANCE_FILE" AXIOM_ADAPTER_FAILURE_FILE="$ADAPTER_FAILURE_FILE" "$AGENT_ADAPTER" "$RUN_DIR/task.md" "$AGENT_WT" >>"$RUN_DIR/stdout.log" 2>>"$RUN_DIR/stderr.log" \
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
  ADAPTER_FAILURE_STATUS=0
  ADAPTER_FAILURE_REASON="$(read_adapter_failure_reason)" || ADAPTER_FAILURE_STATUS=$?
  case "$ADAPTER_FAILURE_STATUS" in
    0) fail_run "$ADAPTER_FAILURE_REASON" ;;
    1) fail_run "agent_execution_failed" ;;
    *) fail_run "adapter_failure_reason_invalid" ;;
  esac
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
if [[ "$RUN_MODE" == "target" ]]; then
  python "$SCRIPT_DIR/run_history.py" mark-superseded \
    --runs-root "$ROOT/runs" \
    --current-record "$RUN_DIR/record.json" \
    >>"$RUN_DIR/stdout.log" 2>>"$RUN_DIR/stderr.log" \
    || fail_run "run_history_update_failed"
fi

echo "RUN_CAPTURED: $RUN_ID"
echo "RUN_DIR: runs/$RUN_ID"
