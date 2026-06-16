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
args = parser.parse_args()

out = {
    "schema_version": 1,
    "run_id": clean(args.run_id),
    "status": args.status,
    "reason": clean(args.reason),
    "branch": clean(args.branch),
    "base_sha": clean(args.base_sha),
    "promotion_commit": clean(args.promotion_commit),
    "timestamp_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
}

Path(args.file).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
