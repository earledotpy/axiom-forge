#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
cd "$ROOT"

echo "AXIOM_FORGE_CHECK: START"
echo "ROOT: $ROOT"
echo

if [[ -n "$(git status --porcelain)" ]]; then
  echo "AXIOM_FORGE_CHECK: FAIL"
  echo "Reason: working tree is dirty"
  git status --short
  exit 1
fi

echo "== Required Adapter CLI Preflight =="
bash scripts/check_adapters.sh

echo
echo "== Gate Contract Matrix =="
bash tests/gate_contract/run_all.sh

echo
echo "== Promotion Matrix =="
bash tests/promote/run_all.sh

echo
echo "== Runner Matrix =="
bash tests/runner/run_all.sh

echo
echo "AXIOM_FORGE_CHECK: PASS"
