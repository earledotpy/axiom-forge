#!/usr/bin/env bash
set -Eeuo pipefail

[[ $# -eq 2 ]] || {
  echo "usage: antigravity.sh <task_file> <worktree>" >&2
  exit 2
}

TASK_FILE="$1"
WORKTREE="$2"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
CONFIG_FILE="$SCRIPT_DIR/../qualification/adapters/antigravity.json"
MODEL="$(python - "$CONFIG_FILE" <<'PY'
import json
import sys
from pathlib import Path

try:
    config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    model = config["selected_model"]
    assert isinstance(model, str) and model
except Exception:
    raise SystemExit("antigravity_qualification_configuration_invalid")

print(model)
PY
)"

python "$SCRIPT_DIR/../scripts/capture_cli_provenance.py" \
  --file "${AXIOM_CLI_PROVENANCE_FILE:-/dev/null}" --command agy

PROMPT="$(
  {
    echo "You are running inside this isolated disposable git worktree:"
    echo "$WORKTREE"
    echo
    echo "Implement the task below by editing files in that worktree only."
    echo "Do not commit."
    echo "Do not create branches."
    echo "Do not modify files outside this worktree."
    echo "Do not run Axiom Forge runner, qualification, promotion, or test-matrix scripts."
    echo "Do not run tests/runner/run_all.sh."
    echo "Do not run scripts/run_agent_task.sh, scripts/qualify_adapter.sh, scripts/promote.sh, scripts/forge_check.sh, or tests/*/run_all.sh."
    echo "Do not create nested worktrees or invoke agents/bad-*.sh."
    echo
    echo "After editing, stop. Do not wait for further instruction."
    echo
    cat "$TASK_FILE"
  }
)"

cd "$WORKTREE"

agy --model "$MODEL" -p "$PROMPT"
