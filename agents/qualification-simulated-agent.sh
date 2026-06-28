#!/usr/bin/env bash
set -Eeuo pipefail

[[ $# -eq 2 ]] || {
  echo "usage: qualification-simulated-agent.sh <task_file> <worktree>" >&2
  exit 2
}

TASK_FILE="$1"
WORKTREE="$2"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

python "$SCRIPT_DIR/../scripts/adapter_identity.py" capture-provenance \
  --command python \
  --file "${AXIOM_CLI_PROVENANCE_FILE:-/dev/null}"

python - "$TASK_FILE" "$WORKTREE/qualification/fixture/message.py" <<'PY'
import re
import sys
from pathlib import Path

task = Path(sys.argv[1]).read_text(encoding="utf-8")
match = re.search(r"returns this exact value:\s*\n\s*([A-Za-z0-9_-]+)", task)
if not match:
    raise SystemExit("task_missing_return_value")

Path(sys.argv[2]).write_text(
    f'def message():\n    return "{match.group(1)}"\n',
    encoding="utf-8",
)
PY
