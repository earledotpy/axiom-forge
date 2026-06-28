#!/usr/bin/env python3
import argparse
import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class QualificationCase:
    name: str
    task_path: Path
    allowed_paths_path: Path
    acceptance_path: Path
    task_repo_path: str
    allowed_paths_repo_path: str
    acceptance_repo_path: str

    @property
    def allowed_paths(self):
        return self.allowed_paths_path.read_text(encoding="utf-8").splitlines()

    @property
    def case_spec(self):
        return {
            "task": {
                "path": self.task_repo_path,
                "sha256": sha256_file(self.task_path),
            },
            "allowed_paths": {
                "path": self.allowed_paths_repo_path,
                "sha256": sha256_file(self.allowed_paths_path),
            },
            "acceptance": {
                "path": self.acceptance_repo_path,
                "sha256": sha256_file(self.acceptance_path),
            },
        }


class QualificationCaseError(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_case(root, name):
    root = Path(root)
    case_dir = root / "qualification" / "cases" / name
    task_path = case_dir / "task.md"
    allowed_paths_path = case_dir / "allowed-paths.txt"
    acceptance_path = case_dir / "accept.sh"

    if not task_path.is_file():
        raise QualificationCaseError("missing_qualification_task")
    if not allowed_paths_path.is_file() or allowed_paths_path.stat().st_size == 0:
        raise QualificationCaseError("missing_qualification_allowed_paths")
    if not acceptance_path.is_file():
        raise QualificationCaseError("missing_qualification_acceptance")

    return QualificationCase(
        name=name,
        task_path=task_path,
        allowed_paths_path=allowed_paths_path,
        acceptance_path=acceptance_path,
        task_repo_path=f"qualification/cases/{name}/task.md",
        allowed_paths_repo_path=f"qualification/cases/{name}/allowed-paths.txt",
        acceptance_repo_path=f"qualification/cases/{name}/accept.sh",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate",))
    parser.add_argument("--root", required=True)
    parser.add_argument("--case", required=True)
    args = parser.parse_args()

    try:
        load_case(args.root, args.case)
    except QualificationCaseError as exc:
        print(exc.reason)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
