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
parser.add_argument("--run-mode", default="forge-local")
parser.add_argument("--target-repo", default=".")
parser.add_argument("--target-name", default="")
parser.add_argument("--target-base-branch", default="")
parser.add_argument("--target-base-sha", default="")
parser.add_argument("--target-remote-url", default="")
parser.add_argument("--target-scope-file", default="")
parser.add_argument("--target-scope-sha256", default="")
parser.add_argument("--delegation-artifact-revision", default="")
parser.add_argument("--delegation-target-base-sha", default="")
parser.add_argument("--delegation-task-file", default="")
parser.add_argument("--superseded-by-run-id", default="")
parser.add_argument("--superseded-reason", default="")
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
    run_mode=args.run_mode,
    target_repo=args.target_repo,
    target_name=args.target_name,
    target_base_branch=args.target_base_branch,
    target_base_sha=args.target_base_sha,
    target_remote_url=args.target_remote_url,
    target_scope_file=args.target_scope_file,
    target_scope_sha256=args.target_scope_sha256,
    delegation_artifact_revision=args.delegation_artifact_revision,
    delegation_target_base_sha=args.delegation_target_base_sha,
    delegation_task_file=args.delegation_task_file,
    superseded_by_run_id=args.superseded_by_run_id,
    superseded_reason=args.superseded_reason,
)
