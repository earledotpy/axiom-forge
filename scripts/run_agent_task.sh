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

RUN_ID="$(date -u +"%Y%m%d-%H%M%S")"
RUN_DIR="$ROOT/runs/$RUN_ID"
BASE_SHA="$(git rev-parse HEAD)"
AGENT_WT="$ROOT/../agent-$RUN_ID"
PATCH_SHA=""

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
    --failure-reason "$reason"
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

"$AGENT_ADAPTER" "$RUN_DIR/task.md" "$AGENT_WT" >>"$RUN_DIR/stdout.log" 2>>"$RUN_DIR/stderr.log" \
  || fail_run "agent_execution_failed"

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
