#!/usr/bin/env python3
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def clean(value):
    return None if value == "" else value


parser = argparse.ArgumentParser()
parser.add_argument("--file", required=True)
parser.add_argument("--run-id", required=True)
parser.add_argument("--agent", required=True)
parser.add_argument("--base-sha", required=True)
parser.add_argument("--status", required=True)
parser.add_argument("--task-file", default="")
parser.add_argument("--patch-file", default="")
parser.add_argument("--patch-sha256", default="")
parser.add_argument("--failure-reason", default="")
parser.add_argument("--cli-command", default="")
parser.add_argument("--cli-path", default="")
parser.add_argument("--cli-version", default="")
args = parser.parse_args()

out = {
    "schema_version": 2,
    "run_id": args.run_id,
    "agent": args.agent,
    "target_repo": ".",
    "base_sha": args.base_sha,
    "task_file": clean(args.task_file),
    "patch_file": clean(args.patch_file),
    "patch_sha256": clean(args.patch_sha256),
    "cli_command": clean(args.cli_command),
    "cli_path": clean(args.cli_path),
    "cli_version": clean(args.cli_version),
    "run_status": args.status,
    "failure_reason": clean(args.failure_reason),
    "timestamp_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
}

Path(args.file).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
