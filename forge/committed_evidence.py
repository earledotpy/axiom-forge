from pathlib import Path

from forge.git import run_git


class CommittedEvidenceError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def read_committed_file(
    root: Path,
    revision: str,
    repo_path: str,
    *,
    missing_reason: str,
    encoding: str | None,
) -> str:
    # Callers deliberately preserve their existing decoding: two use UTF-8 and
    # promotion review uses the locale default. Unifying that drift is a
    # deferred behavior change on the fail-closed gate path.
    result = run_git(root, "show", f"{revision}:{repo_path}", encoding=encoding)
    if result.returncode != 0:
        raise CommittedEvidenceError(missing_reason)
    return result.stdout
