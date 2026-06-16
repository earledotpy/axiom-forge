#!/usr/bin/env python3
import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: json_get.py <json_file> <dotted.key>", file=sys.stderr)
        return 2

    path = Path(sys.argv[1])
    key_path = sys.argv[2].split(".")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        value = data
        for key in key_path:
            value = value[key]
    except Exception as exc:
        print(f"failed to read {sys.argv[2]}: {exc}", file=sys.stderr)
        return 1

    if value is None:
        print("")
    else:
        print(value)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
