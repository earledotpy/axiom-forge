#!/usr/bin/env bash
set -Eeuo pipefail

python - <<'PY'
from pathlib import Path

text = Path("app/target.py").read_text(encoding="utf-8")
raise SystemExit(0 if 'return "after"' in text else 1)
PY