#!/usr/bin/env python3
"""Resolve a CLI and capture its best-effort version for a run record."""

import argparse
import json
import sys
from pathlib import Path

try:
    from adapter_identity import AdapterIdentityError, capture_cli_provenance
except ImportError:
    from scripts.adapter_identity import AdapterIdentityError, capture_cli_provenance


parser = argparse.ArgumentParser()
parser.add_argument("--file", required=True)
parser.add_argument("--command", required=True)
args = parser.parse_args()

try:
    provenance = capture_cli_provenance(args.command)
except AdapterIdentityError as exc:
    print(exc.reason, file=sys.stderr)
    raise SystemExit(127)

Path(args.file).write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
