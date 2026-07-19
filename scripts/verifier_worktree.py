#!/usr/bin/env python3
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forge import subprocess_execution

try:
    from target_task_scope import ChangedPath, TargetTaskScopeError, check_changed_paths_allowed, load_scope_sidecar
except ModuleNotFoundError:
    from scripts.target_task_scope import ChangedPath, TargetTaskScopeError, check_changed_paths_allowed, load_scope_sidecar


VERIFY_WORKTREE_CREATE_FAILED = 10
PATCH_CHECK_FAILED = 20
PATCH_APPLY_FAILED = 21
VERIFICATION_FAILED = 30
PATCH_OUTSIDE_TARGET_TASK_SCOPE = 31


class VerifierError(Exception):
    def __init__(self, returncode):
        super().__init__(str(returncode))
        self.returncode = returncode


def run_command(command, *, cwd=None, stdout=None, stderr=None):
    return subprocess_execution.run(command, cwd=cwd, stdout=stdout, stderr=stderr)


def create_detached_worktree(repo_root, base_sha):
    path = Path(tempfile.mkdtemp())
    path.rmdir()

    completed = run_command(
        ["git", "worktree", "add", "--detach", str(path), base_sha],
        cwd=repo_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
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


def changed_paths_after_apply(worktree):
    completed = subprocess_execution.run(
        ["git", "-C", str(worktree), "diff", "--name-status", "-M", "--no-ext-diff"],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise VerifierError(VERIFICATION_FAILED)

    changed_paths = []
    for line in completed.stdout.splitlines():
        if not line:
            continue
        parts = line.split("\t")
        status = parts[0]
        if status.startswith("R"):
            if len(parts) != 3:
                raise VerifierError(PATCH_OUTSIDE_TARGET_TASK_SCOPE)
            changed_paths.append(ChangedPath(status, parts[2], old_path=parts[1]))
        elif len(parts) == 2:
            changed_paths.append(ChangedPath(status, parts[1]))
        else:
            raise VerifierError(PATCH_OUTSIDE_TARGET_TASK_SCOPE)
    return changed_paths


def enforce_target_task_scope(worktree, scope_file):
    try:
        allowed_paths = load_scope_sidecar(Path(scope_file))
        check_changed_paths_allowed(allowed_paths, changed_paths_after_apply(worktree))
    except TargetTaskScopeError as exc:
        if exc.reason == "target_scope_changed_path_outside_scope":
            raise VerifierError(PATCH_OUTSIDE_TARGET_TASK_SCOPE)
        raise VerifierError(VERIFICATION_FAILED)


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


def verify_target_mode(script_dir, config, worktree, out, record, forge_root, scope_file):
    completed = run_command(
        [
            sys.executable,
            str(Path(script_dir) / "target_verify.py"),
            "run",
            "--config",
            str(config),
            "--worktree",
            str(worktree),
            "--out",
            str(out),
            "--record",
            str(record),
            "--forge-root",
            str(forge_root),
            "--scope-file",
            str(scope_file),
        ]
    )
    if completed.returncode != 0:
        raise VerifierError(VERIFICATION_FAILED)


def verify_detached(
    repo_root,
    script_dir,
    base_sha,
    patch,
    config,
    out,
    verify_mode="forge-local",
    scope_file=None,
    record=None,
    forge_root=None,
):
    worktree = None
    try:
        worktree = create_detached_worktree(repo_root, base_sha)
        apply_patch(worktree, patch)
        if verify_mode == "target":
            enforce_target_task_scope(worktree, scope_file)
            verify_target_mode(script_dir, config, worktree, out, record, forge_root, scope_file)
        else:
            verify_target(script_dir, config, worktree, out)
    finally:
        if worktree is not None:
            remove_worktree(repo_root, worktree)


def main(argv=None):
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify_parser = subparsers.add_parser("verify-detached")
    verify_parser.add_argument("--repo-root", required=True)
    verify_parser.add_argument("--script-dir", required=True)
    verify_parser.add_argument("--base-sha", required=True)
    verify_parser.add_argument("--patch", required=True)
    verify_parser.add_argument("--config", required=True)
    verify_parser.add_argument("--out", required=True)
    verify_parser.add_argument("--verify-mode", choices=("forge-local", "target"), default="forge-local")
    verify_parser.add_argument("--scope-file", default=None)
    verify_parser.add_argument("--record", default=None)
    verify_parser.add_argument("--forge-root", default=None)

    create_parser = subparsers.add_parser("create-detached")
    create_parser.add_argument("--repo-root", required=True)
    create_parser.add_argument("--base-sha", required=True)

    apply_parser = subparsers.add_parser("apply-patch")
    apply_parser.add_argument("--worktree", required=True)
    apply_parser.add_argument("--patch", required=True)

    target_parser = subparsers.add_parser("verify-target")
    target_parser.add_argument("--script-dir", required=True)
    target_parser.add_argument("--config", required=True)
    target_parser.add_argument("--worktree", required=True)
    target_parser.add_argument("--out", required=True)

    args = parser.parse_args(argv)

    try:
        if args.command == "verify-detached":
            verify_detached(
                Path(args.repo_root),
                Path(args.script_dir),
                args.base_sha,
                Path(args.patch),
                Path(args.config),
                Path(args.out),
                args.verify_mode,
                args.scope_file,
                args.record,
                args.forge_root,
            )
        elif args.command == "create-detached":
            worktree = create_detached_worktree(Path(args.repo_root), args.base_sha)
            print(worktree)
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
