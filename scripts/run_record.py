#!/usr/bin/env python3
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


STRICT_SCHEMA_VERSION = 2
COMPLETED = "COMPLETED"
FAILED = "FAILED"

_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_FULL_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")


class RunRecordError(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def clean(value):
    return None if value == "" else value


def is_safe_run_id(value):
    return isinstance(value, str) and _SAFE_RUN_ID.fullmatch(value) is not None


def build_record(
    *,
    run_id,
    agent,
    base_sha,
    status,
    task_file="",
    patch_file="",
    patch_sha256="",
    failure_reason="",
    cli_command="",
    cli_path="",
    cli_version="",
    run_mode="forge-local",
    target_repo=".",
    target_name="",
    target_base_branch="",
    target_base_sha="",
    target_remote_url="",
    target_scope_file="",
    target_scope_sha256="",
    delegation_artifact_revision="",
    delegation_target_base_sha="",
    delegation_task_file="",
):
    return {
        "schema_version": STRICT_SCHEMA_VERSION,
        "run_id": run_id,
        "agent": agent,
        "run_mode": run_mode,
        "target_repo": clean(target_repo),
        "target_name": clean(target_name),
        "target_base_branch": clean(target_base_branch),
        "target_base_sha": clean(target_base_sha),
        "target_remote_url": clean(target_remote_url),
        "target_scope_file": clean(target_scope_file),
        "target_scope_sha256": clean(target_scope_sha256),
        "delegation_artifact_revision": clean(delegation_artifact_revision),
        "delegation_target_base_sha": clean(delegation_target_base_sha),
        "delegation_task_file": clean(delegation_task_file),
        "base_sha": base_sha,
        "task_file": clean(task_file),
        "patch_file": clean(patch_file),
        "patch_sha256": clean(patch_sha256),
        "cli_command": clean(cli_command),
        "cli_path": clean(cli_path),
        "cli_version": clean(cli_version),
        "run_status": status,
        "failure_reason": clean(failure_reason),
        "timestamp_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
    }


def write_record(path, **fields):
    record = build_record(**fields)
    Path(path).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def load_record(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _required_non_empty_string(record, key, reason):
    value = record.get(key)
    if not isinstance(value, str) or value == "":
        raise RunRecordError(reason)
    return value


def _required_full_commit_sha(record, key, missing_reason, malformed_reason):
    value = _required_non_empty_string(record, key, missing_reason)
    if _FULL_COMMIT_SHA.fullmatch(value) is None:
        raise RunRecordError(malformed_reason)
    return value


def validate_completed_record(
    record,
    *,
    run_dir_name=None,
    patch_sha256_actual=None,
    target_scope_sha256_actual=None,
):
    if not isinstance(record, dict):
        raise RunRecordError("missing_run_id")

    run_id = _required_non_empty_string(record, "run_id", "missing_run_id")
    if not is_safe_run_id(run_id):
        raise RunRecordError("unsafe_run_id")

    if run_dir_name is not None and run_id != run_dir_name:
        raise RunRecordError("run_id_directory_mismatch")

    run_status = _required_non_empty_string(record, "run_status", "missing_run_status")
    if run_status != COMPLETED:
        raise RunRecordError("run_not_completed")

    base_sha = _required_non_empty_string(record, "base_sha", "missing_base_sha")
    run_mode = record.get("run_mode", "forge-local")
    if run_mode not in ("forge-local", "target"):
        raise RunRecordError("invalid_run_mode")
    if run_mode == "target":
        _required_non_empty_string(record, "target_name", "missing_target_name")
        _required_non_empty_string(record, "target_repo", "missing_target_repo")
        _required_non_empty_string(record, "target_base_branch", "missing_target_base_branch")
        target_base_sha = _required_non_empty_string(record, "target_base_sha", "missing_target_base_sha")
        _required_non_empty_string(record, "target_remote_url", "missing_target_remote_url")
        target_scope_file = _required_non_empty_string(
            record,
            "target_scope_file",
            "missing_target_scope_file",
        )
        if target_scope_file != "allowed-paths.txt":
            raise RunRecordError("invalid_target_scope_file")
        target_scope_sha256 = _required_non_empty_string(
            record,
            "target_scope_sha256",
            "missing_target_scope_sha256",
        )
        if target_scope_sha256_actual is not None and target_scope_sha256 != target_scope_sha256_actual:
            raise RunRecordError("target_scope_sha256_mismatch")
        if target_base_sha != base_sha:
            raise RunRecordError("target_base_sha_mismatch")
        _required_full_commit_sha(
            record,
            "delegation_artifact_revision",
            "missing_delegation_artifact_revision",
            "malformed_delegation_artifact_revision",
        )
        delegation_target_base_sha = _required_non_empty_string(
            record,
            "delegation_target_base_sha",
            "missing_delegation_target_base_sha",
        )
        if delegation_target_base_sha != target_base_sha:
            raise RunRecordError("delegation_target_base_sha_mismatch")
        _required_non_empty_string(
            record,
            "delegation_task_file",
            "missing_delegation_task_file",
        )

    patch_sha256_expected = record.get("patch_sha256")
    if patch_sha256_expected not in (None, "") and patch_sha256_actual is not None:
        if patch_sha256_expected != patch_sha256_actual:
            raise RunRecordError("patch_sha256_mismatch")

    return {"run_id": run_id, "base_sha": base_sha}


def _add_record_args(parser):
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


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    write_parser = subparsers.add_parser("write")
    _add_record_args(write_parser)

    validate_parser = subparsers.add_parser("validate-completed")
    validate_parser.add_argument("--record", required=True)
    validate_parser.add_argument("--run-dir-name", required=True)
    validate_parser.add_argument("--patch-sha256-actual", default="")
    validate_parser.add_argument("--target-scope-sha256-actual", default="")

    args = parser.parse_args()

    if args.command == "write":
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
        )
        return 0

    if args.command == "validate-completed":
        try:
            record = load_record(args.record)
            validate_completed_record(
                record,
                run_dir_name=args.run_dir_name,
                patch_sha256_actual=clean(args.patch_sha256_actual),
                target_scope_sha256_actual=clean(args.target_scope_sha256_actual),
            )
        except (OSError, json.JSONDecodeError):
            print("missing_run_id")
            return 1
        except RunRecordError as exc:
            print(exc.reason)
            return 1
        return 0

    raise AssertionError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
