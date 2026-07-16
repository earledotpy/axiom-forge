#!/usr/bin/env python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forge.json_shell_vars import JsonShellVarsError, build_payload, extract_assignments, load_payload


def fail(reason: str) -> int:
    print(reason)
    return 1


def extract(arguments: list[str]) -> int:
    if len(arguments) < 3 or arguments[0] not in {"--file", "--json"}:
        return fail("invalid_json_arguments")

    source, source_value, *items = arguments
    keys: list[str] = []
    defaults: dict[str, str] = {}
    while items:
        item, *items = items
        if item == "--default":
            if len(items) < 2:
                return fail("invalid_json_arguments")
            key, default_value, *items = items
            if key in defaults:
                return fail("duplicate_json_field")
            defaults[key] = default_value
            keys.append(key)
        else:
            keys.append(item)
    if not keys:
        return fail("invalid_json_arguments")

    try:
        payload = load_payload(
            json_text=source_value if source == "--json" else None,
            json_file=Path(source_value) if source == "--file" else None,
        )
        print(extract_assignments(payload, keys, defaults))
    except JsonShellVarsError as error:
        return fail(error.reason)
    return 0


def build(arguments: list[str]) -> int:
    fields: list[tuple[str, str]] = []
    while arguments:
        if len(arguments) < 3 or arguments[0] != "--field":
            return fail("invalid_json_arguments")
        _, key, value, *arguments = arguments
        fields.append((key, value))

    try:
        print(build_payload(fields))
    except JsonShellVarsError as error:
        return fail(error.reason)
    return 0


def main(arguments: list[str]) -> int:
    if not arguments:
        return fail("invalid_json_arguments")
    command, *rest = arguments
    if command == "extract":
        return extract(rest)
    if command == "build":
        return build(rest)
    return fail("invalid_json_command")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
