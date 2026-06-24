#!/usr/bin/env python3
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def read_json(path):
    if not path or not Path(path).is_file():
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


parser = argparse.ArgumentParser()
parser.add_argument("--file", required=True)
parser.add_argument("--status", required=True)
parser.add_argument("--stage", required=True)
parser.add_argument("--failure-reason", default="")
parser.add_argument("--adapter", required=True)
parser.add_argument("--case", required=True)
parser.add_argument("--task-file", required=True)
parser.add_argument("--task-source", required=True)
parser.add_argument("--allowed-paths-file", required=True)
parser.add_argument("--acceptance-script", required=True)
parser.add_argument("--record", required=True)
parser.add_argument("--adapter-script", required=True)
parser.add_argument("--adapter-script-revision", default="")
parser.add_argument("--adapter-configuration", default="")
parser.add_argument("--run-validation", required=True)
parser.add_argument("--patch-verification", required=True)
parser.add_argument("--scope", required=True)
parser.add_argument("--acceptance", required=True)
args = parser.parse_args()

record = read_json(args.record)
configuration = read_json(args.adapter_configuration)
adapter_configuration = None
if record is not None:
    adapter_configuration = {
        "adapter_script": args.adapter_script,
        "adapter_script_revision": args.adapter_script_revision or None,
        "cli_command": record.get("cli_command"),
        "cli_path": record.get("cli_path"),
        "cli_version": record.get("cli_version"),
        "selected_model": None if configuration is None else configuration.get("selected_model"),
        "relevant_configuration": None
        if configuration is None
        else configuration.get("relevant_configuration"),
    }

result = {
    "schema_version": 1,
    "timestamp_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "status": args.status,
    "stage": args.stage,
    "failure_reason": args.failure_reason or None,
    "adapter": args.adapter,
    "case": args.case,
    "task_file": args.task_file,
    "allowed_paths": Path(args.allowed_paths_file).read_text(encoding="utf-8").splitlines(),
    "case_spec": {
        "task": {"path": args.task_file, "sha256": sha256_file(args.task_source)},
        "allowed_paths": {
            "path": f"qualification/cases/{args.case}/allowed-paths.txt",
            "sha256": sha256_file(args.allowed_paths_file),
        },
        "acceptance": {
            "path": f"qualification/cases/{args.case}/accept.sh",
            "sha256": sha256_file(args.acceptance_script),
        },
    },
    "run_id": None if record is None else record.get("run_id"),
    "base_sha": None if record is None else record.get("base_sha"),
    "patch_sha256": None if record is None else record.get("patch_sha256"),
    "run_validation": args.run_validation,
    "patch_verification": args.patch_verification,
    "scope": args.scope,
    "acceptance": args.acceptance,
    "adapter_configuration": adapter_configuration,
}

Path(args.file).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
