import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path


def run(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    stdin_mode: str = "inherit",
    text: bool = False,
    capture_output: bool = False,
    timeout: int | None = None,
    check: bool = False,
    env: Mapping[str, str] | None = None,
    stdout=None,
    stderr=None,
):
    if stdin_mode == "inherit":
        stdin = None
    elif stdin_mode == "devnull":
        stdin = subprocess.DEVNULL
    else:
        raise ValueError(f"unknown stdin mode: {stdin_mode}")

    options = {
        "cwd": cwd,
        "text": text,
        "capture_output": capture_output,
        "timeout": timeout,
        "check": check,
        "env": env,
        "stdout": stdout,
        "stderr": stderr,
    }
    if stdin is not None:
        options["stdin"] = stdin

    return subprocess.run(command, **options)
