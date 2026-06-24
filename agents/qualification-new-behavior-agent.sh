#!/usr/bin/env bash
set -Eeuo pipefail

[[ $# -eq 2 ]] || exit 2
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
python "$SCRIPT_DIR/../scripts/capture_cli_provenance.py" \
  --file "${AXIOM_CLI_PROVENANCE_FILE:-/dev/null}" --command python

cat > "$2/qualification/fixture/message.py" <<'PY'
def message():
    return "base"


def greeting(name):
    return f"Hello, {name}!"
PY
