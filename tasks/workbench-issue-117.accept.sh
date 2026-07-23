#!/usr/bin/env bash
set -Eeuo pipefail

python - <<'PY'
from pathlib import Path

text = Path("README.md").read_text(encoding="utf-8")
raise SystemExit(0 if "Workbench end-to-end walk completed on 2026-07-22." in text else 1)
PY