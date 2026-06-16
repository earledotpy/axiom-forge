#!/usr/bin/env python3
import hashlib
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: sha256_file.py <file>", file=sys.stderr)
        return 2

    path = Path(sys.argv[1])
    h = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)

    print(h.hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
