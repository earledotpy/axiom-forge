#!/usr/bin/env python3
import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forge.promotion import write_promotion


def main() -> int:
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
    parser.add_argument("--promotion-review-revision", default="")
    args = parser.parse_args()

    write_promotion(
        args.file,
        run_id=args.run_id,
        status=args.status,
        reason=args.reason,
        branch=args.branch,
        base_sha=args.base_sha,
        promotion_commit=args.promotion_commit,
        target_repo=args.target_repo,
        target_name=args.target_name,
        target_base_branch=args.target_base_branch,
        delegation_target_base_sha=args.delegation_target_base_sha,
        target_remote_url=args.target_remote_url,
        promotion_review_revision=args.promotion_review_revision,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
