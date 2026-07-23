#!/usr/bin/env bash
set -Eeuo pipefail

python - <<'PY'
from pathlib import Path

path = Path("docs/workbench-dogfood.md")
if not path.is_file():
    raise SystemExit(1)
text = path.read_text(encoding="utf-8")
raise SystemExit(0 if "Workbench end-to-end walk completed on 2026-07-22." in text else 1)
PY