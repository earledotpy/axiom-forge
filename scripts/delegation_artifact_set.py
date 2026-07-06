from dataclasses import dataclass
from pathlib import Path

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
    if not acceptance_file.exists():
        return DelegationArtifactSet(
            task_file=task_file.as_posix(),
            scope_file=scope_file.as_posix(),
            acceptance_file=acceptance_file.as_posix(),
            approved_paths=frozenset(),
            state="draft",
            reason="missing_delegation_acceptance_check",
        )

    try:
        approved_paths = load_scope_sidecar(scope_file)
    except TargetTaskScopeError as exc:
        raise DelegationArtifactSetError(exc.reason) from exc

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
