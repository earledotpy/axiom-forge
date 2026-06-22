#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "$SCRIPT_DIR/common.sh"

need_cmd git
need_cmd python

[[ $# -eq 2 ]] || die "usage: run_agent_task.sh <agent_name> <task_file>"

AGENT_NAME="$1"
TASK_FILE="$2"

safe_run_id "$AGENT_NAME" || die "unsafe_agent_name"

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || die "not_inside_git_repo"
cd "$ROOT"

[[ -f "$TASK_FILE" ]] || die "missing_task_file"

if [[ -n "$(git status --porcelain)" ]]; then
  die "target_repo_dirty"
fi

AGENT_ADAPTER="$ROOT/agents/$AGENT_NAME.sh"

RUN_ID="$(python - <<'PYID'
from datetime import datetime, timezone
print(datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f"))
PYID
)"
RUN_DIR="$ROOT/runs/$RUN_ID"
BASE_SHA="$(git rev-parse HEAD)"
AGENT_WT="$ROOT/../agent-$RUN_ID"
PATCH_SHA=""
CLI_PROVENANCE_FILE="$RUN_DIR/cli-provenance.json"
CLI_COMMAND=""
CLI_PATH=""
CLI_VERSION=""

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
    --failure-reason "$reason"
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
    git worktree remove -f "$AGENT_WT" >/dev/null 2>&1 || true
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

{
  echo "RUN_ID=$RUN_ID"
  echo "AGENT_NAME=$AGENT_NAME"
  echo "BASE_SHA=$BASE_SHA"
  echo "TASK_FILE=$TASK_FILE"
  echo "AGENT_ADAPTER=$AGENT_ADAPTER"
} >> "$RUN_DIR/stdout.log"

[[ -x "$AGENT_ADAPTER" ]] || fail_run "agent_adapter_not_found"

git worktree add --detach "$AGENT_WT" "$BASE_SHA" >>"$RUN_DIR/stdout.log" 2>>"$RUN_DIR/stderr.log" \
  || fail_run "agent_worktree_create_failed"

ADAPTER_START_HEAD="$(git -C "$AGENT_WT" rev-parse HEAD)" \
  || fail_run "adapter_start_head_lookup_failed"

BRANCHES_BEFORE="$(git for-each-ref --format="%(refname)" refs/heads)" \
  || fail_run "adapter_branch_snapshot_failed"

TARGET_STATUS_BEFORE="$(git status --porcelain=v1 --untracked-files=all --ignored=matching)" \
  || fail_run "target_repo_status_snapshot_failed"

ADAPTER_EXIT=0
AXIOM_CLI_PROVENANCE_FILE="$CLI_PROVENANCE_FILE" "$AGENT_ADAPTER" "$RUN_DIR/task.md" "$AGENT_WT" >>"$RUN_DIR/stdout.log" 2>>"$RUN_DIR/stderr.log" \
  || ADAPTER_EXIT=$?

TARGET_STATUS_AFTER="$(git status --porcelain=v1 --untracked-files=all --ignored=matching)" \
  || fail_run "target_repo_status_snapshot_failed"

if [[ "$TARGET_STATUS_BEFORE" != "$TARGET_STATUS_AFTER" ]]; then
  fail_run "adapter_modified_outside_worktree"
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

BRANCHES_AFTER="$(git for-each-ref --format="%(refname)" refs/heads)" \
  || fail_run "adapter_branch_snapshot_failed"

if [[ "$BRANCHES_BEFORE" != "$BRANCHES_AFTER" ]]; then
  fail_run "adapter_created_or_deleted_branch"
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
