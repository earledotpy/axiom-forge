from dataclasses import dataclass
from pathlib import Path
import re


class TargetTaskScopeError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ChangedPath:
    status: str
    path: str
    old_path: str | None = None


WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:/")
GLOB_CHARS = set("*?[")


def validate_scope_path(path: str) -> str:
    if "\\" in path:
        raise TargetTaskScopeError("target_scope_backslash_path")
    if path.startswith("/") or WINDOWS_ABSOLUTE_RE.match(path):
        raise TargetTaskScopeError("target_scope_absolute_path")
    if any(char in path for char in GLOB_CHARS):
        raise TargetTaskScopeError("target_scope_glob_path")
    if path.endswith("/") or path == ".":
        raise TargetTaskScopeError("target_scope_directory_entry")

    parts = path.split("/")
    if not parts or any(part == ".." for part in parts):
        raise TargetTaskScopeError("target_scope_traversal")
    if any(part == "." or part == "" for part in parts):
        raise TargetTaskScopeError("target_scope_directory_entry")

    return path


def load_scope_sidecar(path: Path) -> frozenset[str]:
    if not path.exists():
        raise TargetTaskScopeError("target_scope_sidecar_missing")

    allowed = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        allowed.append(validate_scope_path(line))

    if not allowed:
        raise TargetTaskScopeError("target_scope_empty")

    return frozenset(allowed)


def changed_path_names(change: ChangedPath) -> frozenset[str]:
    status = change.status.upper()
    if status.startswith("R"):
        if not change.old_path:
            raise TargetTaskScopeError("target_scope_rename_missing_old_path")
        return frozenset(
            [
                validate_scope_path(change.old_path),
                validate_scope_path(change.path),
            ]
        )
    return frozenset([validate_scope_path(change.path)])


def check_changed_paths_allowed(
    allowed_paths: set[str] | frozenset[str],
    changed_paths: list[ChangedPath],
) -> None:
    allowed = frozenset(validate_scope_path(path) for path in allowed_paths)
    for change in changed_paths:
        for path in changed_path_names(change):
            if path not in allowed:
                raise TargetTaskScopeError("target_scope_changed_path_outside_scope")
