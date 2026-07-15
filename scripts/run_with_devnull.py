#!/usr/bin/env python3
"""Run a command with a valid null standard input on Windows."""

import os
import subprocess
import sys


def main(argv: list[str] | None = None) -> int:
    command = list(sys.argv[1:] if argv is None else argv)
    if not command:
        print("usage: run_with_devnull.py COMMAND [ARG ...]", file=sys.stderr)
        return 2

    if command[0] == "python":
        command[0] = sys.executable

    environment = dict(os.environ)
    environment["AXIOM_FORGE_NORMALIZED_STDIN"] = "1"
    result = subprocess.run(command, stdin=subprocess.DEVNULL, check=False, env=environment)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())