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

    path = Path(sys.argv[1])
    key_path = sys.argv[2].split(".")

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        value = data
        for key in key_path:
            value = value[key]
    except Exception as exc:
        print(f"failed to read {sys.argv[2]}: {exc}", file=sys.stderr)
        return 1

    if isinstance(value, bool):
        print("true" if value else "false")
    elif isinstance(value, (str, int, float)):
        print(value)
    else:
        print(value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
