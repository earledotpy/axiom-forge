#!/usr/bin/env python3
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

try:
    from adapter_identity import (
        build_identity_evidence,
        build_partial_identity_evidence,
        identity_for,
    )
    from qualification_case import load_case
except ImportError:
    from scripts.adapter_identity import (
        build_identity_evidence,
        build_partial_identity_evidence,
        identity_for,
    )
    from scripts.qualification_case import load_case


CASES = {"behavior-change", "new-behavior", "edge-case"}


def read_json(path):
    if not path or not Path(path).is_file():
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def utc_now():
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def build_result(
    *,
    root,
    status,
    stage,
    failure_reason,
    adapter,
    case,
    record_path,
    adapter_script,
    adapter_script_revision,
    adapter_configuration_path,
    run_validation,
    patch_verification,
    scope,
    acceptance,
):
    qualification_case = load_case(root, case)
    record = read_json(record_path)
    configuration = read_json(adapter_configuration_path)
    adapter_configuration = None
    if record is not None:
        try:
            adapter_configuration = build_identity_evidence(
                adapter_script=adapter_script,
                adapter_script_revision=adapter_script_revision,
                record=record,
                adapter_configuration=configuration,
            )
        except Exception:
            adapter_configuration = build_partial_identity_evidence(
                adapter_script=adapter_script,
                adapter_script_revision=adapter_script_revision,
                record=record,
                adapter_configuration=configuration,
            )

    return {
        "schema_version": 1,
        "timestamp_utc": utc_now(),
        "status": status,
        "stage": stage,
        "failure_reason": failure_reason or None,
        "adapter": adapter,
        "case": case,
        "task_file": qualification_case.task_repo_path,
        "allowed_paths": qualification_case.allowed_paths,
        "case_spec": qualification_case.case_spec,
        "run_id": None if record is None else record.get("run_id"),
        "base_sha": None if record is None else record.get("base_sha"),
        "patch_sha256": None if record is None else record.get("patch_sha256"),
        "run_validation": run_validation,
        "patch_verification": patch_verification,
        "scope": scope,
        "acceptance": acceptance,
        "adapter_configuration": adapter_configuration,
    }


def write_result(path, **kwargs):
    result = build_result(**kwargs)
    Path(path).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def load_result(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"invalid_result:{path}:{exc}") from exc


def load_results_for_adapter(root, adapter):
    """Return qualification results for an adapter sorted by filename (chronological by run-ID)."""
    rd = Path(root) / "qualification" / "results" / adapter
    if not rd.is_dir():
        return []
    return [load_result(str(p)) for p in sorted(rd.glob("*.json"))]


def check_results_clean(root, adapter):
    """Raise ValueError if qualification/results/<adapter>/ has uncommitted changes."""
    rel = f"qualification/results/{adapter}"
    proc = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain", "--", rel],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise ValueError(f"git_status_failed:{adapter}")
    if proc.stdout.strip():
        raise ValueError(f"results_not_committed:{adapter}")


def summary(result):
    return {
        "run_id": result.get("run_id"),
        "case": result.get("case"),
        "patch_sha256": result.get("patch_sha256"),
        "case_spec": result.get("case_spec"),
        "scope": result.get("scope"),
        "acceptance": result.get("acceptance"),
    }


def result_failure_reason(result):
    if result.get("status") != "PASSED":
        return "failed_result"
    if any(
        result.get(field) != "PASSED"
        for field in ("run_validation", "patch_verification", "scope", "acceptance")
    ):
        return "failed_result"
    case_spec = result.get("case_spec")
    if (
        not isinstance(case_spec, dict)
        or not result.get("run_id")
        or not result.get("patch_sha256")
    ):
        return "incomplete_result"
    for field in ("task", "allowed_paths", "acceptance"):
        item = case_spec.get(field)
        if not isinstance(item, dict) or not item.get("path") or not item.get("sha256"):
            return "incomplete_result"
    return None


def evaluate(results):
    active = []
    pinned_configuration = None
    last_reason = "series_incomplete"
    resets = []

    for result in results:
        case = result.get("case")
        run_id = result.get("run_id")
        identity = identity_for(result.get("adapter_configuration"))

        failure_reason = result_failure_reason(result)
        if failure_reason is not None:
            active = []
            pinned_configuration = None
            last_reason = failure_reason
            resets.append({"run_id": run_id, "reason": last_reason})
            continue
        if identity is None:
            active = []
            pinned_configuration = None
            last_reason = "missing_identity"
            resets.append({"run_id": run_id, "reason": last_reason})
            continue
        if case not in CASES:
            active = []
            pinned_configuration = None
            last_reason = "unknown_case"
            resets.append({"run_id": run_id, "reason": last_reason})
            continue
        if pinned_configuration is not None and identity != pinned_configuration:
            active = []
            pinned_configuration = identity
            last_reason = "configuration_drift"
            resets.append({"run_id": run_id, "reason": last_reason})
        elif pinned_configuration is None:
            pinned_configuration = identity

        if any(previous.get("case") == case for previous in active):
            active = []
            last_reason = "duplicate_case"
            resets.append({"run_id": run_id, "reason": last_reason})

        active.append(result)

    qualified = {result.get("case") for result in active} == CASES
    return {
        "schema_version": 1,
        "status": "QUALIFIED" if qualified else "NOT_QUALIFIED",
        "reason": None if qualified else last_reason,
        "adapter": active[-1].get("adapter") if active else None,
        "pinned_configuration": pinned_configuration if active else None,
        "qualifying_results": [summary(result) for result in active],
        "resets": resets,
    }
