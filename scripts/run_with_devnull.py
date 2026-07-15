#!/usr/bin/env python3
"""Run a command with a valid null standard input on Windows."""

import subprocess
import sys


def main(argv: list[str] | None = None) -> int:
    command = list(sys.argv[1:] if argv is None else argv)
    if not command:
        print("usage: run_with_devnull.py COMMAND [ARG ...]", file=sys.stderr)
        return 2

    if command[0] == "python":
        command[0] = sys.executable

    result = subprocess.run(command, stdin=subprocess.DEVNULL, check=False)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())