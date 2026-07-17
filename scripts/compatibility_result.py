#!/usr/bin/env python3
import json
from pathlib import Path

import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forge.small_helpers import (
    read_optional_json,
    sha256_file as shared_sha256_file,
    utc_now as shared_utc_now,
)

try:
    from adapter_identity import build_partial_identity_evidence
except ImportError:
    from scripts.adapter_identity import build_partial_identity_evidence


def read_json(path):
    return read_optional_json(path)


def sha256_file(path):
    return shared_sha256_file(path)


def utc_now():
    return shared_utc_now()


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
