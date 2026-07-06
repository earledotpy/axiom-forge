#!/usr/bin/env python3
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def clean(value):
    return None if value == "" else value


parser = argparse.ArgumentParser()
parser.add_argument("--file", required=True)
parser.add_argument("--run-id", default="")
parser.add_argument("--status", required=True)
parser.add_argument("--reason", default="")
parser.add_argument("--branch", default="")
parser.add_argument("--base-sha", default="")
parser.add_argument("--promotion-commit", default="")
parser.add_argument("--target-repo", default="")
parser.add_argument("--target-name", default="")
parser.add_argument("--target-base-branch", default="")
parser.add_argument("--delegation-target-base-sha", default="")
parser.add_argument("--target-remote-url", default="")
args = parser.parse_args()

out = {
    "schema_version": 1,
    "run_id": clean(args.run_id),
    "status": args.status,
    "reason": clean(args.reason),
    "branch": clean(args.branch),
    "base_sha": clean(args.base_sha),
    "promotion_commit": clean(args.promotion_commit),
    "target_repo": clean(args.target_repo),
    "target_name": clean(args.target_name),
    "target_base_branch": clean(args.target_base_branch),
    "delegation_target_base_sha": clean(args.delegation_target_base_sha),
    "target_remote_url": clean(args.target_remote_url),
    "timestamp_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
}

Path(args.file).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
