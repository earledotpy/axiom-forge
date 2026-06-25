#!/usr/bin/env bash
set -Eeuo pipefail

[[ $# -eq 2 ]] || {
  echo "usage: cursor.sh <task_file> <worktree>" >&2
  exit 2
}

TASK_FILE="$1"
WORKTREE="$2"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
if [[ -n "${USERPROFILE:-}" ]] && command -v cygpath >/dev/null 2>&1; then
  CURSOR_AGENT_DIRECT_BIN="$(cygpath -u "$USERPROFILE")/AppData/Local/cursor-agent"
  if [[ -x "$CURSOR_AGENT_DIRECT_BIN/cursor-agent.cmd" ]]; then
    export PATH="$CURSOR_AGENT_DIRECT_BIN:$PATH"
  fi
fi

python "$SCRIPT_DIR/../scripts/capture_cli_provenance.py" \
  --file "${AXIOM_CLI_PROVENANCE_FILE:-/dev/null}" --command cursor-agent.cmd

mkdir -p "$WORKTREE/.cursor"
cat > "$WORKTREE/.cursor/cli.json" <<'JSON'
{
  "version": 1,
  "editor": { "vimMode": false },
  "permissions": {
    "allow": ["Read(*)", "Write(*)"],
    "deny": [
      "Shell(*)",
      "Read(.env*)",
      "Read(**/.env*)",
      "Write(.env*)",
      "Write(**/.env*)",
      "Mcp(*:*)",
      "WebFetch(*)"
    ]
  }
}
JSON

PROMPT="$(
  {
    echo "You are running inside this isolated disposable git worktree:"
    echo "$WORKTREE"
    echo
    echo "Implement the task between the TASK markers below by editing tracked task files in that worktree only."
    echo "Do not commit."
    echo "Do not create branches."
    echo "Do not modify files outside this worktree."
    echo "Do not run shell commands, git commands, Axiom Forge runner, qualification, promotion, or test-matrix scripts."
    echo "Do not run tests/runner/run_all.sh."
    echo "Do not run scripts/run_agent_task.sh, scripts/qualify_adapter.sh, scripts/promote.sh, scripts/forge_check.sh, or tests/*/run_all.sh."
    echo "Do not create nested worktrees or invoke agents/bad-*.sh."
    echo
    echo "After editing, stop. Do not wait for further instruction."
    echo
    echo "TASK BEGINS"
    cat "$TASK_FILE"
    echo "TASK ENDS"
  }
)"

cursor-agent.cmd \
  --print \
  --force \
  --workspace "$WORKTREE" \
  --sandbox disabled \
  --output-format json \
  "$PROMPT"