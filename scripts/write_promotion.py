#!/usr/bin/env python3
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def none_if_empty(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--status", required=True)
    parser.add_argument("--reason", default="")
    parser.add_argument("--branch", default="")
    parser.add_argument("--base-sha", default="")
    parser.add_argument("--promotion-commit", default="")
    parser.add_argument("--pre-verification", default="")
    parser.add_argument("--post-verification", default="")
    args = parser.parse_args()

    out = {
        "schema_version": 1,
        "run_id": none_if_empty(args.run_id),
        "status": args.status,
        "reason": none_if_empty(args.reason),
        "branch": none_if_empty(args.branch),
        "base_sha": none_if_empty(args.base_sha),
        "promotion_commit": none_if_empty(args.promotion_commit),
        "operator_confirmed_run_id": args.status == "PROMOTED",
        "pre_promotion_verification": none_if_empty(args.pre_verification),
        "post_promotion_verification": none_if_empty(args.post_verification),
        "timestamp_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }

    path = Path(args.file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
