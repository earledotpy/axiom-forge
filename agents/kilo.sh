#!/usr/bin/env bash
set -Eeuo pipefail

[[ $# -eq 2 ]] || {
  echo "usage: kilo.sh <task_file> <worktree>" >&2
  exit 2
}

TASK_FILE="$1"
WORKTREE="$2"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
if [[ -n "${USERPROFILE:-}" ]] && command -v cygpath >/dev/null 2>&1; then
  KILO_DIRECT_BIN="$(cygpath -u "$USERPROFILE")/.npm-global"
  if [[ -x "$KILO_DIRECT_BIN/kilo" ]]; then
    export PATH="$KILO_DIRECT_BIN:$PATH"
  fi
fi

python "$SCRIPT_DIR/../scripts/capture_cli_provenance.py" \
  --file "${AXIOM_CLI_PROVENANCE_FILE:-/dev/null}" --command kilo

mkdir -p "$WORKTREE/.kilo/agents"
TASK_COPY="$WORKTREE/.kilo/axiom-task.md"
cp "$TASK_FILE" "$TASK_COPY"

cat > "$WORKTREE/.kilo/agents/axiom-forge.md" <<'AGENT'
---
description: Axiom Forge isolated worktree adapter agent
mode: primary
permission:
  read: allow
  edit: allow
  write: allow
  glob: allow
  grep: allow
  bash: deny
  webfetch: deny
  websearch: deny
  task: deny
  agent_manager: deny
  skill: deny
  lsp: deny
  external_directory: deny
  todowrite: deny
  todoread: deny
---
You are restricted to the supplied disposable git worktree.
AGENT

PROMPT="You are running inside this isolated disposable git worktree: $WORKTREE. Read the task file at $TASK_COPY and implement it by editing tracked task files in that worktree only. Do not commit. Do not create branches. Do not modify files outside this worktree. Do not run shell commands, git commands, Axiom Forge runner, qualification, promotion, or test-matrix scripts. Do not run tests/runner/run_all.sh. Do not run scripts/run_agent_task.sh, scripts/qualify_adapter.sh, scripts/promote.sh, scripts/forge_check.sh, or tests/*/run_all.sh. Do not create nested worktrees or invoke agents/bad-*.sh. Do not use remote sessions, remote control, worktree creation, MCP servers, plugins, hooks, skills, subagents, or external commands. After editing, stop. Do not wait for further instruction."

kilo run \
  --dir "$WORKTREE" \
  --agent axiom-forge \
  --format json \
  --pure \
  --auto \
  --title axiom-forge-kilo-adapter-run \
  "$PROMPT"
