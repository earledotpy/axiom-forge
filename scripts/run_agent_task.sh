#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "$SCRIPT_DIR/common.sh"

need_cmd git
need_cmd python

[[ $# -eq 2 ]] || die "usage: run_agent_task.sh <agent_name> <task_file>"

AGENT_NAME="$1"
TASK_FILE="$2"

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || die "not_inside_git_repo"
cd "$ROOT"

[[ -f "$TASK_FILE" ]] || die "missing_task_file"

if [[ -n "$(git status --porcelain)" ]]; then
  die "target_repo_dirty"
fi

RUN_ID="$(date -u +"%Y%m%d-%H%M%S")"
RUN_DIR="$ROOT/runs/$RUN_ID"
BASE_SHA="$(git rev-parse HEAD)"
AGENT_WT="$ROOT/../agent-$RUN_ID"
PATCH_SHA=""
FAILURE_REASON=""

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
} >> "$RUN_DIR/stdout.log"

if [[ "$AGENT_NAME" != "manual-simulated-agent" ]]; then
  fail_run "unsupported_agent_for_v0_1"
fi

git worktree add --detach "$AGENT_WT" "$BASE_SHA" >>"$RUN_DIR/stdout.log" 2>>"$RUN_DIR/stderr.log" \
  || fail_run "agent_worktree_create_failed"

python - "$RUN_DIR/task.md" "$AGENT_WT/app/target.py" >>"$RUN_DIR/stdout.log" 2>>"$RUN_DIR/stderr.log" <<'PY' \
  || fail_run "agent_execution_failed"
import re
import sys
from pathlib import Path

task_path = Path(sys.argv[1])
target_path = Path(sys.argv[2])

task = task_path.read_text(encoding="utf-8")
match = re.search(r"returns this exact value:\s*\n\s*([A-Za-z0-9_-]+)", task)

if not match:
    raise SystemExit("task_missing_return_value")

value = match.group(1)

target_path.write_text(
    f'def answer():\n    return "{value}"\n',
    encoding="utf-8",
)

print(f"manual simulated agent wrote answer() return value: {value}")
PY

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
