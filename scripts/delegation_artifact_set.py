from dataclasses import dataclass
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess

try:
    from target_task_scope import TargetTaskScopeError, load_scope_sidecar
except ModuleNotFoundError:
    from scripts.target_task_scope import TargetTaskScopeError, load_scope_sidecar


class DelegationArtifactSetError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class DelegationArtifactSet:
    task_file: str
    scope_file: str
    acceptance_file: str
    approved_paths: frozenset[str]
    state: str
    reason: str | None = None


def _task_stem(task_file: Path) -> str:
    if task_file.name.endswith(".task.md"):
        return task_file.name[: -len(".task.md")]
    raise DelegationArtifactSetError("invalid_delegation_task_file")


def scope_sidecar_path(task_file: Path) -> Path:
    task_file = Path(task_file)
    return task_file.with_name(f"{_task_stem(task_file)}.allowed-paths.txt")


def acceptance_check_path(task_file: Path) -> Path:
    task_file = Path(task_file)
    return task_file.with_name(f"{_task_stem(task_file)}.accept.sh")


def load_task_artifact_set(task_file: Path) -> DelegationArtifactSet:
    task_file = Path(task_file)
    if not task_file.exists():
        raise DelegationArtifactSetError("missing_delegation_task_file")

    scope_file = scope_sidecar_path(task_file)
    acceptance_file = acceptance_check_path(task_file)

    if not scope_file.exists():
        return DelegationArtifactSet(
            task_file=task_file.as_posix(),
            scope_file=scope_file.as_posix(),
            acceptance_file=acceptance_file.as_posix(),
            approved_paths=frozenset(),
            state="draft",
            reason="missing_delegation_scope_file",
        )

    try:
        approved_paths = load_scope_sidecar(scope_file)
    except TargetTaskScopeError as exc:
        raise DelegationArtifactSetError(exc.reason) from exc

    if not acceptance_file.exists():
        return DelegationArtifactSet(
            task_file=task_file.as_posix(),
            scope_file=scope_file.as_posix(),
            acceptance_file=acceptance_file.as_posix(),
            approved_paths=approved_paths,
            state="draft",
            reason="missing_delegation_acceptance_check",
        )

    if not acceptance_file.read_text(encoding="utf-8").strip():
        return DelegationArtifactSet(
            task_file=task_file.as_posix(),
            scope_file=scope_file.as_posix(),
            acceptance_file=acceptance_file.as_posix(),
            approved_paths=approved_paths,
            state="draft",
            reason="empty_delegation_acceptance_check",
        )

    return DelegationArtifactSet(
        task_file=task_file.as_posix(),
        scope_file=scope_file.as_posix(),
        acceptance_file=acceptance_file.as_posix(),
        approved_paths=approved_paths,
        state="delegation-ready",
    )


def load_delegation_ready_artifact_set(task_file: Path) -> DelegationArtifactSet | None:
    artifact_set = load_task_artifact_set(task_file)
    if artifact_set.state == "delegation-ready":
        return artifact_set
    return None


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError as exc:
        raise DelegationArtifactSetError("invalid_delegation_task_file") from exc


def validate_delegation_task_file(path: str) -> PurePosixPath:
    if "\\" in path:
        raise DelegationArtifactSetError("malformed_delegation_task_file")
    pure = PurePosixPath(path)
    parts = pure.parts
    if pure.is_absolute() or not parts or any(part in ("", ".", "..") for part in parts):
        raise DelegationArtifactSetError("malformed_delegation_task_file")
    if not path.startswith("tasks/") or not path.endswith(".task.md"):
        raise DelegationArtifactSetError("malformed_delegation_task_file")
    return pure


def acceptance_repo_path_for_task(task_file: str) -> str:
    task_path = validate_delegation_task_file(task_file)
    name = str(task_path)
    return f"{name[:-len('.task.md')]}.accept.sh"

def _committed_file_content(root: Path, revision: str, repo_path: str, missing_reason: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "show", f"{revision}:{repo_path}"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise DelegationArtifactSetError(missing_reason)
    return result.stdout


def committed_acceptance_artifact(
    *,
    forge_root: Path,
    delegation_artifact_revision: str,
    delegation_task_file: str,
    scope_file: Path,
) -> dict[str, str]:
    try:
        allowed_paths = load_scope_sidecar(Path(scope_file))
    except TargetTaskScopeError as exc:
        raise DelegationArtifactSetError(exc.reason) from exc

    acceptance_path = acceptance_repo_path_for_task(delegation_task_file)
    if acceptance_path in allowed_paths:
        raise DelegationArtifactSetError("target_acceptance_check_in_scope")

    content = _committed_file_content(
        Path(forge_root),
        delegation_artifact_revision,
        acceptance_path,
        "missing_target_acceptance_check",
    )
    if not content.strip() or "\x00" in content or "\r" in content:
        raise DelegationArtifactSetError("invalid_target_acceptance_check")

    return {
        "path": acceptance_path,
        "revision": delegation_artifact_revision,
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "content": content,
    }


def committed_acceptance_artifact_from_record(
    *,
    forge_root: Path,
    record: dict,
    scope_file: Path,
) -> dict[str, str]:
    revision = record.get("delegation_artifact_revision")
    if not isinstance(revision, str) or not revision:
        raise DelegationArtifactSetError("missing_delegation_artifact_revision")
    task_file = record.get("delegation_task_file")
    if not isinstance(task_file, str) or not task_file:
        raise DelegationArtifactSetError("missing_delegation_task_file")
    return committed_acceptance_artifact(
        forge_root=forge_root,
        delegation_artifact_revision=revision,
        delegation_task_file=task_file,
        scope_file=scope_file,
    )

def prepare_target_run_artifacts(
    *,
    task_file: Path,
    run_dir: Path,
    forge_root: Path,
    delegation_artifact_revision: str,
) -> dict[str, str]:
    forge_root = Path(forge_root).resolve()
    task_file = Path(task_file)
    if not task_file.is_absolute():
        task_file = forge_root / task_file
    task_file = task_file.resolve()
    run_dir = Path(run_dir)

    try:
        artifact_set = load_task_artifact_set(task_file)
    except DelegationArtifactSetError as exc:
        if exc.reason in {"target_scope_sidecar_missing", "missing_delegation_scope_file"}:
            raise DelegationArtifactSetError("missing_target_task_scope") from exc
        if exc.reason == "target_scope_empty":
            raise DelegationArtifactSetError("empty_target_task_scope") from exc
        if exc.reason.startswith("target_scope_"):
            raise DelegationArtifactSetError("invalid_target_task_scope") from exc
        raise

    if artifact_set.state != "delegation-ready":
        if artifact_set.reason == "missing_delegation_scope_file":
            raise DelegationArtifactSetError("missing_target_task_scope")
        if artifact_set.reason == "missing_delegation_acceptance_check":
            raise DelegationArtifactSetError("missing_target_acceptance_check")
        if artifact_set.reason == "empty_delegation_acceptance_check":
            raise DelegationArtifactSetError("invalid_target_acceptance_check")
        raise DelegationArtifactSetError(artifact_set.reason or "invalid_delegation_artifact_set")

    acceptance_file = Path(artifact_set.acceptance_file)
    acceptance_repo_path = _repo_relative(acceptance_file.resolve(), forge_root)
    if acceptance_repo_path in artifact_set.approved_paths:
        raise DelegationArtifactSetError("target_acceptance_check_in_scope")

    content = _committed_file_content(
        forge_root,
        delegation_artifact_revision,
        acceptance_repo_path,
        "missing_target_acceptance_check",
    )
    if not content.strip():
        raise DelegationArtifactSetError("invalid_target_acceptance_check")

    copied_scope = run_dir / "allowed-paths.txt"
    try:
        shutil.copyfile(artifact_set.scope_file, copied_scope)
    except OSError as exc:
        raise DelegationArtifactSetError("target_task_scope_copy_failed") from exc
    if not copied_scope.exists() or copied_scope.stat().st_size == 0:
        raise DelegationArtifactSetError("empty_target_task_scope")

    try:
        target_scope_sha256 = _sha256_file(copied_scope)
    except OSError as exc:
        raise DelegationArtifactSetError("target_task_scope_sha256_compute_failed") from exc

    return {
        "target_scope_file": "allowed-paths.txt",
        "target_scope_sha256": target_scope_sha256,
        "delegation_artifact_revision": delegation_artifact_revision,
        "delegation_task_file": _repo_relative(task_file, forge_root),
    }


def _cmd_prepare_target_run(args: argparse.Namespace) -> int:
    try:
        result = prepare_target_run_artifacts(
            task_file=Path(args.task_file),
            run_dir=Path(args.run_dir),
            forge_root=Path(args.forge_root),
            delegation_artifact_revision=args.delegation_artifact_revision,
        )
    except DelegationArtifactSetError as exc:
        print(exc.reason)
        return 1

    print(json.dumps(result, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare-target-run")
    prepare_parser.add_argument("--task-file", required=True)
    prepare_parser.add_argument("--run-dir", required=True)
    prepare_parser.add_argument("--forge-root", required=True)
    prepare_parser.add_argument("--delegation-artifact-revision", required=True)
    prepare_parser.set_defaults(func=_cmd_prepare_target_run)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
