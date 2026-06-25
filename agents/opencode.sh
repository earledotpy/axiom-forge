#!/usr/bin/env bash
set -Eeuo pipefail

[[ $# -eq 2 ]] || {
  echo "usage: opencode.sh <task_file> <worktree>" >&2
  exit 2
}

TASK_FILE="$1"
WORKTREE="$2"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
if [[ -n "${USERPROFILE:-}" ]] && command -v cygpath >/dev/null 2>&1; then
  OPENCODE_DIRECT_BIN="$(cygpath -u "$USERPROFILE")/.opencode/bin"
  if [[ -x "$OPENCODE_DIRECT_BIN/opencode.exe" ]]; then
    export PATH="$OPENCODE_DIRECT_BIN:$PATH"
  fi
fi

python "$SCRIPT_DIR/../scripts/capture_cli_provenance.py" \
  --file "${AXIOM_CLI_PROVENANCE_FILE:-/dev/null}" --command opencode

OPENCODE_CONFIG_CONTENT="$(cat <<'JSON'
{
  "$schema": "https://opencode.ai/config.json",
  "permission": {
    "*": "deny",
    "read": {
      "*": "allow",
      "*.env": "deny",
      "*.env.*": "deny",
      "*.env.example": "allow"
    },
    "edit": {
      "*": "allow"
    },
    "glob": {
      "*": "allow"
    },
    "grep": {
      "*": "allow"
    },
    "bash": {
      "*": "deny"
    },
    "external_directory": {
      "*": "deny"
    },
    "webfetch": "deny",
    "websearch": "deny",
    "question": "deny",
    "task": {
      "*": "deny"
    }
  },
  "agent": {
    "build": {
      "permission": {
        "*": "deny",
        "read": {
          "*": "allow",
          "*.env": "deny",
          "*.env.*": "deny",
          "*.env.example": "allow"
        },
        "edit": {
          "*": "allow"
        },
        "glob": {
          "*": "allow"
        },
        "grep": {
          "*": "allow"
        },
        "bash": {
          "*": "deny"
        },
        "external_directory": {
          "*": "deny"
        },
        "webfetch": "deny",
        "websearch": "deny",
        "question": "deny",
        "task": {
          "*": "deny"
        }
      }
    }
  }
}
JSON
)"
export OPENCODE_CONFIG_CONTENT

PROMPT="$(
  {
    echo "You are running inside this isolated disposable git worktree:"
    echo "$WORKTREE"
    echo
    echo "Implement the task below by editing files in that worktree only."
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
    cat "$TASK_FILE"
  }
)"

opencode run \
  --dir "$WORKTREE" \
  --agent build \
  --format json \
  --pure \
  --title axiom-forge-opencode-adapter-run \
  "$PROMPT"
