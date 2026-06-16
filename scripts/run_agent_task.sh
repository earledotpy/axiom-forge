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

if [[ "$AGENT_NAME" != "manual-simulated-agent" ]]; then
  die "unsupported_agent_for_v0_1"
fi

RUN_ID="$(date -u +"%Y%m%d-%H%M%S")"
RUN_DIR="$ROOT/runs/$RUN_ID"
BASE_SHA="$(git rev-parse HEAD)"
AGENT_WT="$ROOT/../agent-$RUN_ID"

mkdir -p "$RUN_DIR"

cp "$TASK_FILE" "$RUN_DIR/task.md"

cleanup() {
  if [[ -d "$AGENT_WT" ]]; then
    git worktree remove -f "$AGENT_WT" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

{
  echo "RUN_ID=$RUN_ID"
  echo "AGENT_NAME=$AGENT_NAME"
  echo "BASE_SHA=$BASE_SHA"
  echo "TASK_FILE=$TASK_FILE"
} > "$RUN_DIR/stdout.log"

: > "$RUN_DIR/stderr.log"

git worktree add --detach "$AGENT_WT" "$BASE_SHA" >>"$RUN_DIR/stdout.log" 2>>"$RUN_DIR/stderr.log"

python - "$RUN_DIR/task.md" "$AGENT_WT/app/target.py" >>"$RUN_DIR/stdout.log" 2>>"$RUN_DIR/stderr.log" <<'PY'
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

git -C "$AGENT_WT" diff --binary > "$RUN_DIR/patch.diff"

if [[ ! -s "$RUN_DIR/patch.diff" ]]; then
  die "agent_produced_empty_patch"
fi

PATCH_SHA="$(python "$SCRIPT_DIR/sha256_file.py" "$RUN_DIR/patch.diff")"

cat > "$RUN_DIR/record.json" <<JSON
{
  "schema_version": 1,
  "run_id": "$RUN_ID",
  "agent": "$AGENT_NAME",
  "target_repo": ".",
  "base_sha": "$BASE_SHA",
  "patch_file": "patch.diff",
  "patch_sha256": "$PATCH_SHA",
  "run_status": "COMPLETED"
}
JSON

echo "RUN_CAPTURED: $RUN_ID"
echo "RUN_DIR: runs/$RUN_ID"
