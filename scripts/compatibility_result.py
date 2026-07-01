#!/usr/bin/env python3
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

try:
    from adapter_identity import build_partial_identity_evidence
except ImportError:
    from scripts.adapter_identity import build_partial_identity_evidence


def read_json(path):
    if not path or not Path(path).is_file():
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc_now():
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def build_result(
    *,
    status,
    stage,
    failure_reason,
    adapter,
    task_file,
    task_source,
    record_path,
    adapter_script,
    adapter_script_revision,
    adapter_configuration_path,
    run_validation,
    patch_verification,
):
    record = read_json(record_path)
    configuration = read_json(adapter_configuration_path)
    task_source = Path(task_source)

    return {
        "schema_version": 1,
        "result_type": "candidate_adapter_compatibility",
        "timestamp_utc": utc_now(),
        "status": status,
        "stage": stage,
        "failure_reason": failure_reason or None,
        "adapter": adapter,
        "task": {
            "path": task_file,
            "sha256": sha256_file(task_source) if task_source.is_file() else None,
        },
        "run_id": None if record is None else record.get("run_id"),
        "base_sha": None if record is None else record.get("base_sha"),
        "patch_sha256": None if record is None else record.get("patch_sha256"),
        "run_status": None if record is None else record.get("run_status"),
        "run_failure_reason": None if record is None else record.get("failure_reason"),
        "run_validation": run_validation,
        "patch_verification": patch_verification,
        "adapter_configuration": build_partial_identity_evidence(
            adapter_script=adapter_script,
            adapter_script_revision=adapter_script_revision,
            record=record,
            adapter_configuration=configuration,
        ),
        "compatibility_decision": "COMPATIBLE"
        if status == "COMPATIBLE"
        else "INCOMPATIBLE",
        "standard_trust_decision": "NOT_STANDARD_TRUST",
        "promotion_decision": "NOT_PROMOTION_APPROVAL",
    }


def write_result(path, **kwargs):
    result = build_result(**kwargs)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result
