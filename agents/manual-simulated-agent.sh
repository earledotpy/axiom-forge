#!/usr/bin/env bash
set -Eeuo pipefail

[[ $# -eq 2 ]] || {
  echo "usage: manual-simulated-agent.sh <task_file> <worktree>" >&2
  exit 2
}

TASK_FILE="$1"
WORKTREE="$2"

python - "$TASK_FILE" "$WORKTREE/app/target.py" <<'PY'
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
