#!/usr/bin/env python3
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    print("Python 3.11+ required: missing tomllib", file=sys.stderr)
    sys.exit(2)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: toml_get.py <toml_file> <dotted.key>", file=sys.stderr)
        return 2

    data = tomllib.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    value = data
    for key in sys.argv[2].split("."):
        value = value[key]

    print(value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
