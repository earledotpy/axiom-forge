#!/usr/bin/env bash
set -Eeuo pipefail

[[ $# -eq 2 ]] || {
  echo "usage: new-file-only-agent.sh <task_file> <worktree>" >&2
  exit 2
}

WORKTREE="$2"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

python "$SCRIPT_DIR/../scripts/capture_cli_provenance.py" \
  --file "${AXIOM_CLI_PROVENANCE_FILE:-/dev/null}" --command python

mkdir -p "$WORKTREE/docs"
printf 'Workbench end-to-end walk completed on 2026-07-22.\n' \
  > "$WORKTREE/docs/workbench-dogfood.md"
