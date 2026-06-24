#!/usr/bin/env python3
"""Evaluate an ordered, contiguous adapter-qualification result series."""

import argparse
import json
import sys
from pathlib import Path


CASES = {"behavior-change", "new-behavior", "edge-case"}
IDENTITY_FIELDS = (
    "adapter_script",
    "adapter_script_revision",
    "cli_command",
    "cli_path",
    "cli_version",
    "selected_model",
    "relevant_configuration",
)


def load_result(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"invalid_result:{path}:{exc}") from exc


def identity_for(result):
    configuration = result.get("adapter_configuration")
    if not isinstance(configuration, dict):
        return None
    if any(not configuration.get(field) for field in IDENTITY_FIELDS):
        return None
    if not isinstance(configuration["relevant_configuration"], dict):
        return None
    return {field: configuration[field] for field in IDENTITY_FIELDS}


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
    if any(result.get(field) != "PASSED" for field in ("run_validation", "patch_verification", "scope", "acceptance")):
        return "failed_result"
    case_spec = result.get("case_spec")
    if not isinstance(case_spec, dict) or not result.get("run_id") or not result.get("patch_sha256"):
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
        identity = identity_for(result)

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


parser = argparse.ArgumentParser()
parser.add_argument("results", nargs="+", help="qualification.json files, oldest to newest")
args = parser.parse_args()

try:
    outcome = evaluate([load_result(path) for path in args.results])
except ValueError as exc:
    print(str(exc), file=sys.stderr)
    raise SystemExit(2)

print(json.dumps(outcome, indent=2, sort_keys=True))
