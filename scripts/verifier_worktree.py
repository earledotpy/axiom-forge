#!/usr/bin/env python3
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


VERIFY_WORKTREE_CREATE_FAILED = 10
PATCH_CHECK_FAILED = 20
PATCH_APPLY_FAILED = 21
VERIFICATION_FAILED = 30


class VerifierError(Exception):
    def __init__(self, returncode):
        super().__init__(str(returncode))
        self.returncode = returncode


def run_command(command, *, cwd=None):
    return subprocess.run(command, cwd=cwd)


def create_detached_worktree(repo_root, base_sha):
    path = Path(tempfile.mkdtemp())
    path.rmdir()

    completed = run_command(
        ["git", "worktree", "add", "--detach", str(path), base_sha],
        cwd=repo_root,
    )
    if completed.returncode != 0:
        raise VerifierError(VERIFY_WORKTREE_CREATE_FAILED)

    return path


def remove_worktree(repo_root, worktree):
    if Path(worktree).is_dir():
        run_command(
            ["git", "worktree", "remove", "-f", str(worktree)],
            cwd=repo_root,
        )


def check_patch(worktree, patch):
    completed = run_command(
        ["git", "-C", str(worktree), "apply", "--check", "--whitespace=error", str(patch)]
    )
    if completed.returncode != 0:
        raise VerifierError(PATCH_CHECK_FAILED)


def apply_patch(worktree, patch):
    check_patch(worktree, patch)
    completed = run_command(
        ["git", "-C", str(worktree), "apply", "--whitespace=error", str(patch)]
    )
    if completed.returncode != 0:
        raise VerifierError(PATCH_APPLY_FAILED)


def verify_target(script_dir, config, worktree, out):
    completed = run_command(
        [
            sys.executable,
            str(Path(script_dir) / "verify_target.py"),
            "--config",
            str(config),
            "--worktree",
            str(worktree),
            "--out",
            str(out),
        ]
    )
    if completed.returncode != 0:
        raise VerifierError(VERIFICATION_FAILED)


def verify_detached(repo_root, script_dir, base_sha, patch, config, out):
    worktree = None
    try:
        worktree = create_detached_worktree(repo_root, base_sha)
        apply_patch(worktree, patch)
        verify_target(script_dir, config, worktree, out)
    finally:
        if worktree is not None:
            remove_worktree(repo_root, worktree)


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify_parser = subparsers.add_parser("verify-detached")
    verify_parser.add_argument("--repo-root", required=True)
    verify_parser.add_argument("--script-dir", required=True)
    verify_parser.add_argument("--base-sha", required=True)
    verify_parser.add_argument("--patch", required=True)
    verify_parser.add_argument("--config", required=True)
    verify_parser.add_argument("--out", required=True)

    apply_parser = subparsers.add_parser("apply-patch")
    apply_parser.add_argument("--worktree", required=True)
    apply_parser.add_argument("--patch", required=True)

    target_parser = subparsers.add_parser("verify-target")
    target_parser.add_argument("--script-dir", required=True)
    target_parser.add_argument("--config", required=True)
    target_parser.add_argument("--worktree", required=True)
    target_parser.add_argument("--out", required=True)

    args = parser.parse_args()

    try:
        if args.command == "verify-detached":
            verify_detached(
                Path(args.repo_root),
                Path(args.script_dir),
                args.base_sha,
                Path(args.patch),
                Path(args.config),
                Path(args.out),
            )
        elif args.command == "apply-patch":
            apply_patch(Path(args.worktree), Path(args.patch))
        elif args.command == "verify-target":
            verify_target(
                Path(args.script_dir),
                Path(args.config),
                Path(args.worktree),
                Path(args.out),
            )
        else:
            raise AssertionError(f"unknown command: {args.command}")
    except VerifierError as exc:
        return exc.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
