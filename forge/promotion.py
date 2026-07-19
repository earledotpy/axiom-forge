import json
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = 1
_REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "run_id",
        "status",
        "reason",
        "branch",
        "base_sha",
        "promotion_commit",
        "target_repo",
        "target_name",
        "target_base_branch",
        "delegation_target_base_sha",
        "target_remote_url",
        "promotion_review_revision",
        "timestamp_utc",
    }
)
_OPTIONAL_STRING_FIELDS = _REQUIRED_FIELDS - {"schema_version", "status", "timestamp_utc"}


def clean(value: str) -> str | None:
    return None if value == "" else value


def _timestamp_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_promotion(
    *,
    run_id: str,
    status: str,
    reason: str = "",
    branch: str = "",
    base_sha: str = "",
    promotion_commit: str = "",
    target_repo: str = "",
    target_name: str = "",
    target_base_branch: str = "",
    delegation_target_base_sha: str = "",
    target_remote_url: str = "",
    promotion_review_revision: str = "",
) -> dict:
    record = {
        "schema_version": SCHEMA_VERSION,
        "run_id": clean(run_id),
        "status": status,
        "reason": clean(reason),
        "branch": clean(branch),
        "base_sha": clean(base_sha),
        "promotion_commit": clean(promotion_commit),
        "target_repo": clean(target_repo),
        "target_name": clean(target_name),
        "target_base_branch": clean(target_base_branch),
        "delegation_target_base_sha": clean(delegation_target_base_sha),
        "target_remote_url": clean(target_remote_url),
        "promotion_review_revision": clean(promotion_review_revision),
        "timestamp_utc": _timestamp_utc(),
    }
    validate_promotion(record)
    return record


def validate_promotion(record: dict) -> None:
    if not isinstance(record, dict) or set(record) != _REQUIRED_FIELDS:
        raise ValueError("invalid promotion evidence schema")
    if record["schema_version"] != SCHEMA_VERSION:
        raise ValueError("invalid promotion evidence schema")
    if not isinstance(record["status"], str):
        raise ValueError("invalid promotion evidence schema")
    if not isinstance(record["timestamp_utc"], str) or record["timestamp_utc"] == "":
        raise ValueError("invalid promotion evidence schema")
    if any(record[field] is not None and not isinstance(record[field], str) for field in _OPTIONAL_STRING_FIELDS):
        raise ValueError("invalid promotion evidence schema")


def write_promotion(path: Path | str, **fields: str) -> dict:
    record = build_promotion(**fields)
    Path(path).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record
