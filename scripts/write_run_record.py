#!/usr/bin/env python3
import argparse
from run_record import write_record


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

write_record(
    args.file,
    run_id=args.run_id,
    agent=args.agent,
    base_sha=args.base_sha,
    status=args.status,
    task_file=args.task_file,
    patch_file=args.patch_file,
    patch_sha256=args.patch_sha256,
    failure_reason=args.failure_reason,
    cli_command=args.cli_command,
    cli_path=args.cli_path,
    cli_version=args.cli_version,
)
