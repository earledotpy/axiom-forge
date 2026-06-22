#!/usr/bin/env python3
"""Resolve a CLI and capture its best-effort version for a run record."""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("--file", required=True)
parser.add_argument("--command", required=True)
args = parser.parse_args()

path = shutil.which(args.command)
if path is None:
    print(f"{args.command}_cli_not_found", file=sys.stderr)
    raise SystemExit(127)

try:
    resolved_path = str(Path(path).resolve())
except OSError:
    resolved_path = path

version = None
try:
    result = subprocess.run(
        [resolved_path, "--version"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=10,
        check=False,
    )
    version = next((line.strip() for line in result.stdout.splitlines() if line.strip()), None)
except (OSError, subprocess.SubprocessError):
    pass

Path(args.file).write_text(
    json.dumps(
        {
            "cli_command": args.command,
            "cli_path": resolved_path,
            "cli_version": version,
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
