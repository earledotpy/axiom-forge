import json
import re
import shlex
from collections.abc import Mapping, Sequence
from pathlib import Path


class JsonShellVarsError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def load_payload(*, json_text: str | None, json_file: Path | None) -> Mapping[str, object]:
    try:
        if json_text is not None:
            payload = json.loads(json_text)
        elif json_file is not None:
            payload = json.loads(json_file.read_text(encoding="utf-8"))
        else:
            raise JsonShellVarsError("invalid_json_arguments")
    except JsonShellVarsError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise JsonShellVarsError("invalid_json_payload") from None

    if not isinstance(payload, dict):
        raise JsonShellVarsError("invalid_json_payload")
    return payload


def extract_assignments(
    payload: Mapping[str, object],
    keys: Sequence[str],
    defaults: Mapping[str, str] | None = None,
) -> str:
    defaults = defaults or {}
    assignments = []
    for key in keys:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise JsonShellVarsError("invalid_json_field")
        if key not in payload:
            if key not in defaults:
                raise JsonShellVarsError(f"missing_json_key_{key}")
            value = defaults[key]
        else:
            value = payload[key]
        if value is None:
            value = ""
        elif not isinstance(value, str):
            value = str(value)
        assignments.append(f"{key}={shlex.quote(value)}")
    return "\n".join(assignments)


def build_payload(fields: Sequence[tuple[str, str]]) -> str:
    payload: dict[str, str] = {}
    for key, value in fields:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise JsonShellVarsError("invalid_json_field")
        if key in payload:
            raise JsonShellVarsError("duplicate_json_field")
        payload[key] = value
    return json.dumps(payload, separators=(",", ":"))
