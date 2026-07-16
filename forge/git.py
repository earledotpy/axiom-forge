import subprocess
from pathlib import Path


def run_git(
    root: Path, *args: str, encoding: str | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        capture_output=True,
        check=False,
        encoding=encoding,
    )
