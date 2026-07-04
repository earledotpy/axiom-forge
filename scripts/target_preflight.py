#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    print("Python 3.11+ required: missing tomllib", file=sys.stderr)
    sys.exit(2)


class PreflightFailure(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def normalize_path(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def is_inside(child: Path, parent: Path) -> bool:
    child_norm = normalize_path(child)
    parent_norm = normalize_path(parent)
    return child_norm == parent_norm or child_norm.startswith(parent_norm + os.sep)


def require_string(config: dict, key: str) -> str:
    value = config.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PreflightFailure("target_config_malformed")
    return value


def require_verify_config(config: dict) -> tuple[list[str], int]:
    verify = config.get("verify")
    if not isinstance(verify, dict):
        raise PreflightFailure("target_verification_config_missing")

    command = verify.get("command")
    if (
        not isinstance(command, list)
        or not command
        or any(not isinstance(part, str) or not part for part in command)
    ):
        raise PreflightFailure("target_verification_config_missing")

    timeout = verify.get("timeout_seconds")
    if not isinstance(timeout, int) or timeout <= 0:
        raise PreflightFailure("target_verification_config_missing")

    return command, timeout


def load_primary_target(config_path: Path) -> dict:
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        raise PreflightFailure("target_config_malformed")

    try:
        primary = config["target"]["primary"]
    except KeyError:
        raise PreflightFailure("target_config_missing")

    if not isinstance(primary, dict):
        raise PreflightFailure("target_config_malformed")

    require_string(primary, "name")
    require_string(primary, "repo_path")
    require_string(primary, "expected_base_branch")
    require_string(primary, "expected_remote_url")
    require_verify_config(primary)
    return primary


def validate_target(config_path: Path, forge_root: Path) -> dict:
    primary = load_primary_target(config_path)
    target_path = Path(primary["repo_path"]).expanduser()
    if not target_path.is_absolute():
        target_path = (config_path.parent / target_path).resolve()

    if not target_path.exists():
        raise PreflightFailure("target_repo_path_missing")

    target_path = target_path.resolve()
    forge_root = forge_root.resolve()

    if is_inside(target_path, forge_root):
        raise PreflightFailure("target_repo_inside_forge_checkout")

    git_root_result = run_git(target_path, "rev-parse", "--show-toplevel")
    if git_root_result.returncode != 0:
        raise PreflightFailure("target_repo_not_git_repository")

    git_root = Path(git_root_result.stdout.strip()).resolve()
    if normalize_path(git_root) != normalize_path(target_path):
        raise PreflightFailure("target_repo_path_not_git_root")

    remote_result = run_git(target_path, "remote", "get-url", "origin")
    if remote_result.returncode != 0:
        raise PreflightFailure("target_remote_unavailable")

    expected_remote = primary["expected_remote_url"]
    actual_remote = remote_result.stdout.strip()
    if actual_remote != expected_remote:
        raise PreflightFailure("target_remote_mismatch")

    branch_result = run_git(target_path, "branch", "--show-current")
    if branch_result.returncode != 0:
        raise PreflightFailure("target_branch_unavailable")

    expected_branch = primary["expected_base_branch"]
    actual_branch = branch_result.stdout.strip()
    if actual_branch != expected_branch:
        raise PreflightFailure("target_not_on_expected_base_branch")

    status_result = run_git(target_path, "status", "--porcelain")
    if status_result.returncode != 0:
        raise PreflightFailure("target_status_unavailable")
    if status_result.stdout.strip():
        raise PreflightFailure("target_repo_dirty")

    base_result = run_git(target_path, "rev-parse", f"{expected_branch}^{{commit}}")
    if base_result.returncode != 0 or not base_result.stdout.strip():
        raise PreflightFailure("target_base_sha_unresolved")

    command, timeout = require_verify_config(primary)
    return {
        "target_name": primary["name"],
        "target_repo": str(target_path),
        "base_branch": expected_branch,
        "base_sha": base_result.stdout.strip(),
        "remote_url": actual_remote,
        "verify_command": command,
        "verify_timeout_seconds": timeout,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="gate.toml")
    parser.add_argument("--forge-root", default=None)
    parser.add_argument("--json-output", default=None)
    args = parser.parse_args(argv)

    config_path = Path(args.config).resolve()
    forge_root = Path(args.forge_root).resolve() if args.forge_root else config_path.parent

    try:
        result = validate_target(config_path, forge_root)
    except PreflightFailure as exc:
        print("TARGET_PREFLIGHT: FAIL")
        print(f"Reason: {exc.reason}")
        return 1

    print("TARGET_PREFLIGHT: PASS")
    print(f"Target: {result['target_name']}")
    print(f"Repo: {result['target_repo']}")
    print(f"Base: {result['base_branch']} {result['base_sha']}")
    if args.json_output:
        Path(args.json_output).write_text(
            json.dumps(result, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
