#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forge.small_helpers import sha256_file


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: sha256_file.py <file>", file=sys.stderr)
        return 2

    path = Path(sys.argv[1])
    print(sha256_file(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
