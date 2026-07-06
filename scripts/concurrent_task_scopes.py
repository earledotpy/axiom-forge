from dataclasses import dataclass
from pathlib import Path

try:
    from delegation_artifact_set import (
        DelegationArtifactSetError,
        acceptance_check_path as artifact_acceptance_check_path,
        load_delegation_ready_artifact_set,
        scope_sidecar_path as artifact_scope_sidecar_path,
    )
except ModuleNotFoundError:
    from scripts.delegation_artifact_set import (
        DelegationArtifactSetError,
        acceptance_check_path as artifact_acceptance_check_path,
        load_delegation_ready_artifact_set,
        scope_sidecar_path as artifact_scope_sidecar_path,
    )


class ConcurrentTaskScopeError(Exception):
    def __init__(self, reason: str, conflicts: list["ConcurrentTaskScopeConflict"] | None = None):
        super().__init__(reason)
        self.reason = reason
        self.conflicts = conflicts or []


@dataclass(frozen=True)
class DelegationTaskScope:
    task_file: str
    scope_file: str
    acceptance_file: str
    approved_paths: frozenset[str]


@dataclass(frozen=True)
class ConcurrentTaskScopeConflict:
    first_task_file: str
    second_task_file: str
    overlapping_paths: tuple[str, ...]


def scope_sidecar_path(task_file: Path) -> Path:
    try:
        return artifact_scope_sidecar_path(task_file)
    except DelegationArtifactSetError as exc:
        raise ConcurrentTaskScopeError(exc.reason) from exc


def acceptance_check_path(task_file: Path) -> Path:
    try:
        return artifact_acceptance_check_path(task_file)
    except DelegationArtifactSetError as exc:
        raise ConcurrentTaskScopeError(exc.reason) from exc


def load_delegation_ready_task(task_file: Path) -> DelegationTaskScope | None:
    try:
        artifact_set = load_delegation_ready_artifact_set(task_file)
    except DelegationArtifactSetError as exc:
        raise ConcurrentTaskScopeError(exc.reason) from exc

    if artifact_set is None:
        return None

    return DelegationTaskScope(
        task_file=artifact_set.task_file,
        scope_file=artifact_set.scope_file,
        acceptance_file=artifact_set.acceptance_file,
        approved_paths=artifact_set.approved_paths,
    )


def load_active_delegation_ready_tasks(
    task_files: list[Path],
) -> list[DelegationTaskScope]:
    ready_tasks = []
    for task_file in task_files:
        task = load_delegation_ready_task(task_file)
        if task is not None:
            ready_tasks.append(task)
    return ready_tasks


def find_concurrent_task_scope_conflicts(
    tasks: list[DelegationTaskScope],
) -> list[ConcurrentTaskScopeConflict]:
    conflicts = []
    for first_index, first in enumerate(tasks):
        for second in tasks[first_index + 1 :]:
            overlap = tuple(sorted(first.approved_paths & second.approved_paths))
            if overlap:
                conflicts.append(
                    ConcurrentTaskScopeConflict(
                        first_task_file=first.task_file,
                        second_task_file=second.task_file,
                        overlapping_paths=overlap,
                    )
                )
    return conflicts


def check_concurrent_task_scopes(task_files: list[Path]) -> list[DelegationTaskScope]:
    tasks = load_active_delegation_ready_tasks(task_files)
    conflicts = find_concurrent_task_scope_conflicts(tasks)
    if conflicts:
        raise ConcurrentTaskScopeError(
            "concurrent_task_scope_conflict",
            conflicts,
        )
    return tasks
