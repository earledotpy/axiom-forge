#!/usr/bin/env bash
set -Eeuo pipefail

[[ $# -eq 1 ]] || {
  echo "usage: accept.sh <verifier-worktree>" >&2
  exit 2
}

python - "$1" <<'PY'
import sys

sys.path.insert(0, sys.argv[1])
from qualification.fixture.message import greeting, message

assert greeting("Ada") == "Hello, Ada!"
assert greeting("Lin") == "Hello, Lin!"
assert message() == "base"
PY
