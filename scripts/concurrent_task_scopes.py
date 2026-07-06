from dataclasses import dataclass
from pathlib import Path

try:
    from target_task_scope import TargetTaskScopeError, load_scope_sidecar
except ModuleNotFoundError:
    from scripts.target_task_scope import TargetTaskScopeError, load_scope_sidecar


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
    if task_file.name.endswith(".task.md"):
        return task_file.with_name(f"{task_file.name[:-len('.task.md')]}.allowed-paths.txt")
    raise ConcurrentTaskScopeError("invalid_delegation_task_file")


def acceptance_check_path(task_file: Path) -> Path:
    if task_file.name.endswith(".task.md"):
        return task_file.with_name(f"{task_file.name[:-len('.task.md')]}.accept.sh")
    raise ConcurrentTaskScopeError("invalid_delegation_task_file")


def load_delegation_ready_task(task_file: Path) -> DelegationTaskScope | None:
    if not task_file.exists():
        raise ConcurrentTaskScopeError("missing_delegation_task_file")

    scope_file = scope_sidecar_path(task_file)
    acceptance_file = acceptance_check_path(task_file)

    if not scope_file.exists() or not acceptance_file.exists():
        return None

    try:
        approved_paths = load_scope_sidecar(scope_file)
    except TargetTaskScopeError as exc:
        raise ConcurrentTaskScopeError(exc.reason) from exc

    if not acceptance_file.read_text(encoding="utf-8").strip():
        return None

    return DelegationTaskScope(
        task_file=task_file.as_posix(),
        scope_file=scope_file.as_posix(),
        acceptance_file=acceptance_file.as_posix(),
        approved_paths=approved_paths,
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
