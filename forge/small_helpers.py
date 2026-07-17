import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def read_optional_json(path: str | Path | None) -> object | None:
    if not path or not Path(path).is_file():
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_json_object(path: Path, *, error: Exception) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise error from exc
    if not isinstance(value, dict):
        raise error
    return value


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def require_nonempty_string(
    record: dict,
    key: str,
    *,
    error: Exception,
    strip: bool = False,
) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value or (strip and not value.strip()):
        raise error
    return value
