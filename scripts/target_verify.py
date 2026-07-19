#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forge import subprocess_execution
from forge.small_helpers import (
    load_json_object,
    require_nonempty_string,
    utc_now as shared_utc_now,
)

from scripts.delegation_artifact_set import (
    DelegationArtifactSetError,
    committed_acceptance_artifact_from_record,
    validate_delegation_task_file as validate_delegation_task_path,
)
from scripts.target_preflight import PreflightFailure, is_inside, load_primary_target, normalize_path

class TargetVerifyFailure(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def utc_now() -> str:
    return shared_utc_now()


def load_record(path: Path) -> dict:
    return load_json_object(path, error=TargetVerifyFailure("target_record_malformed"))


def require_string(record: dict, key: str, reason: str) -> str:
    return require_nonempty_string(record, key, error=TargetVerifyFailure(reason))


def configured_target_path(config_path: Path, target: dict) -> Path:
    path = Path(target["repo_path"]).expanduser()
    if not path.is_absolute():
        path = config_path.parent / path
    return path.resolve()


def validate_delegation_task_file(path: str) -> None:
    try:
        validate_delegation_task_path(path)
    except DelegationArtifactSetError as exc:
        raise TargetVerifyFailure(exc.reason) from exc


def validate_acceptance_artifact(
    *,
    forge_root: Path,
    record: dict,
    scope_file: Path,
) -> dict:
    try:
        return committed_acceptance_artifact_from_record(
            forge_root=forge_root,
            record=record,
            scope_file=scope_file,
        )
    except DelegationArtifactSetError as exc:
        raise TargetVerifyFailure(exc.reason) from exc


def validate_context(record_path: Path, config_path: Path, forge_root: Path) -> dict:
    try:
        target = load_primary_target(config_path)
    except PreflightFailure as exc:
        raise TargetVerifyFailure(exc.reason)

    record = load_record(record_path)
    run_mode = record.get("run_mode", "forge-local")
    if run_mode != "target":
        raise TargetVerifyFailure("target_flag_requires_target_run")

    target_name = require_string(record, "target_name", "missing_target_name")
    target_repo = require_string(record, "target_repo", "missing_target_repo")
    target_base_branch = require_string(record, "target_base_branch", "missing_target_base_branch")
    target_base_sha = require_string(record, "target_base_sha", "missing_target_base_sha")
    delegation_target_base_sha = require_string(
        record,
        "delegation_target_base_sha",
        "missing_delegation_target_base_sha",
    )
    target_remote_url = require_string(record, "target_remote_url", "missing_target_remote_url")
    base_sha = require_string(record, "base_sha", "missing_base_sha")
    task_file = require_string(record, "delegation_task_file", "missing_delegation_task_file")
    validate_delegation_task_file(task_file)

    if target_base_sha != base_sha:
        raise TargetVerifyFailure("target_base_sha_mismatch")
    if delegation_target_base_sha != target_base_sha:
        raise TargetVerifyFailure("delegation_target_base_sha_mismatch")
    if target_name != target["name"]:
        raise TargetVerifyFailure("target_name_mismatch")
    if target_base_branch != target["expected_base_branch"]:
        raise TargetVerifyFailure("target_base_branch_mismatch")
    if target_remote_url != target["expected_remote_url"]:
        raise TargetVerifyFailure("target_remote_mismatch")

    configured_repo = configured_target_path(config_path, target)
    recorded_repo = Path(target_repo).expanduser()
    if not recorded_repo.is_absolute():
        recorded_repo = (record_path.parent / recorded_repo).resolve()
    recorded_repo = recorded_repo.resolve()

    if normalize_path(recorded_repo) != normalize_path(configured_repo):
        raise TargetVerifyFailure("target_repo_mismatch")

    forge_root = forge_root.resolve()
    if is_inside(recorded_repo, forge_root):
        raise TargetVerifyFailure("target_repo_inside_forge_checkout")

    if not recorded_repo.exists():
        raise TargetVerifyFailure("target_repo_path_missing")

    remote = subprocess.run(
        ["git", "-C", str(recorded_repo), "remote", "get-url", "origin"],
        text=True,
        capture_output=True,
        check=False,
    )
    if remote.returncode != 0:
        raise TargetVerifyFailure("target_remote_unavailable")
    if remote.stdout.strip() != target_remote_url:
        raise TargetVerifyFailure("target_remote_mismatch")

    commit = subprocess.run(
        ["git", "-C", str(recorded_repo), "cat-file", "-e", f"{delegation_target_base_sha}^{{commit}}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if commit.returncode != 0:
        raise TargetVerifyFailure("target_base_sha_not_found")

    return {"repo_root": str(recorded_repo), "base_sha": delegation_target_base_sha}


def run_check(command, *, cwd: Path, timeout: int) -> tuple[dict, str | None]:
    check = {
        "command": command,
        "returncode": None,
        "stdout": "",
        "stderr": "",
    }
    try:
        completed = subprocess_execution.run(
            command,
            cwd=cwd,
            stdin_mode="devnull",
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        check["returncode"] = completed.returncode
        check["stdout"] = completed.stdout
        check["stderr"] = completed.stderr
        if completed.returncode == 0:
            return check, None
        return check, "target_verification_failed"
    except subprocess.TimeoutExpired as exc:
        check["stdout"] = exc.stdout or ""
        check["stderr"] = exc.stderr or ""
        return check, "target_verification_timeout"
    except Exception as exc:
        check["stderr"] = str(exc)
        return check, "target_verification_error"


def run_acceptance_check(artifact: dict, *, worktree: Path, timeout: int) -> tuple[dict, str | None]:
    script_path = None
    check = {
        "path": artifact["path"],
        "revision": artifact["revision"],
        "sha256": artifact["sha256"],
        "command": ["bash", artifact["path"]],
        "returncode": None,
        "stdout": "",
        "stderr": "",
    }
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".accept.sh", delete=False) as handle:
            handle.write(artifact["content"])
            script_path = Path(handle.name)
        stdin_mode = "inherit" if os.environ.get("AXIOM_FORGE_NORMALIZED_STDIN") == "1" else "devnull"
        completed = subprocess_execution.run(
            ["bash", str(script_path)],
            cwd=worktree,
            stdin_mode=stdin_mode,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        check["returncode"] = completed.returncode
        check["stdout"] = completed.stdout
        check["stderr"] = completed.stderr
        if completed.returncode == 0:
            return check, None
        return check, "target_acceptance_failed"
    except subprocess.TimeoutExpired as exc:
        check["stdout"] = exc.stdout or ""
        check["stderr"] = exc.stderr or ""
        return check, "target_acceptance_timeout"
    except Exception as exc:
        check["stderr"] = str(exc)
        return check, "target_acceptance_error"
    finally:
        try:
            if script_path is not None:
                script_path.unlink()
        except Exception:
            pass


def run_target_verification(
    config_path: Path,
    worktree: Path,
    out: Path,
    record_path: Path,
    forge_root: Path,
    scope_file: Path,
) -> int:
    result = {
        "schema_version": 1,
        "status": "FAIL",
        "timestamp_utc": utc_now(),
        "worktree": str(worktree),
        "check": {},
        "acceptance": {},
    }
    try:
        target = load_primary_target(config_path)
        command = target["verify"]["command"]
        timeout = target["verify"]["timeout_seconds"]
        record = load_record(record_path)
        artifact = validate_acceptance_artifact(
            forge_root=forge_root,
            record=record,
            scope_file=scope_file,
        )
    except TargetVerifyFailure as exc:
        result["reason"] = exc.reason
        out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print("VERIFY_TARGET_MODE: FAIL")
        print(f"Reason: {exc.reason}")
        return 1
    except Exception as exc:
        result["reason"] = f"target_verification_config_missing: {exc}"
        out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print("VERIFY_TARGET_MODE: FAIL")
        print("Reason: target_verification_config_missing")
        return 1

    target_check, reason = run_check(command, cwd=worktree, timeout=timeout)
    result["check"] = target_check
    if reason is not None:
        result["reason"] = reason
    else:
        acceptance_check, reason = run_acceptance_check(artifact, worktree=worktree, timeout=timeout)
        result["acceptance"] = acceptance_check
        if reason is None:
            result["status"] = "PASS"
        else:
            result["reason"] = reason

    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"VERIFY_TARGET_MODE: {result['status']}")
    if result["status"] == "PASS":
        return 0
    print(f"Reason: {result.get('reason', 'target_verification_failed')}")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    context_parser = subparsers.add_parser("validate-context")
    context_parser.add_argument("--record", required=True)
    context_parser.add_argument("--config", required=True)
    context_parser.add_argument("--forge-root", required=True)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--config", required=True)
    run_parser.add_argument("--worktree", required=True)
    run_parser.add_argument("--out", required=True)
    run_parser.add_argument("--record", required=True)
    run_parser.add_argument("--forge-root", required=True)
    run_parser.add_argument("--scope-file", required=True)

    args = parser.parse_args(argv)

    if args.command == "validate-context":
        try:
            context = validate_context(
                Path(args.record),
                Path(args.config).resolve(),
                Path(args.forge_root).resolve(),
            )
        except TargetVerifyFailure as exc:
            print(exc.reason)
            return 1
        print(json.dumps(context, sort_keys=True))
        return 0

    if args.command == "run":
        return run_target_verification(
            Path(args.config).resolve(),
            Path(args.worktree).resolve(),
            Path(args.out),
            Path(args.record),
            Path(args.forge_root).resolve(),
            Path(args.scope_file),
        )

    raise AssertionError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
