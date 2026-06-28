#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


IDENTITY_FIELDS = (
    "adapter_script",
    "adapter_script_revision",
    "cli_command",
    "cli_path",
    "cli_version",
    "selected_model",
    "relevant_configuration",
)


class AdapterIdentityError(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def read_json(path):
    if not path or not Path(path).is_file():
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def require_adapter_configuration(configuration):
    if not isinstance(configuration, dict):
        raise AdapterIdentityError("adapter_configuration_incomplete")
    if not isinstance(configuration.get("selected_model"), str):
        raise AdapterIdentityError("adapter_configuration_incomplete")
    if not configuration["selected_model"]:
        raise AdapterIdentityError("adapter_configuration_incomplete")
    if not isinstance(configuration.get("relevant_configuration"), dict):
        raise AdapterIdentityError("adapter_configuration_incomplete")
    return configuration


def require_cli_provenance(record):
    if not isinstance(record, dict):
        raise AdapterIdentityError("cli_provenance_incomplete")
    for key in ("cli_command", "cli_path", "cli_version"):
        if not isinstance(record.get(key), str) or not record[key]:
            raise AdapterIdentityError("cli_provenance_incomplete")
    return record


def build_identity_evidence(
    *,
    adapter_script,
    adapter_script_revision,
    record,
    adapter_configuration,
):
    configuration = require_adapter_configuration(adapter_configuration)
    provenance = require_cli_provenance(record)
    return {
        "adapter_script": adapter_script,
        "adapter_script_revision": adapter_script_revision or None,
        "cli_command": provenance.get("cli_command"),
        "cli_path": provenance.get("cli_path"),
        "cli_version": provenance.get("cli_version"),
        "selected_model": configuration.get("selected_model"),
        "relevant_configuration": configuration.get("relevant_configuration"),
    }


def build_partial_identity_evidence(
    *,
    adapter_script,
    adapter_script_revision,
    record,
    adapter_configuration,
):
    record = record if isinstance(record, dict) else {}
    adapter_configuration = (
        adapter_configuration if isinstance(adapter_configuration, dict) else {}
    )
    return {
        "adapter_script": adapter_script,
        "adapter_script_revision": adapter_script_revision or None,
        "cli_command": record.get("cli_command"),
        "cli_path": record.get("cli_path"),
        "cli_version": record.get("cli_version"),
        "selected_model": adapter_configuration.get("selected_model"),
        "relevant_configuration": adapter_configuration.get("relevant_configuration"),
    }


def identity_for(configuration):
    if not isinstance(configuration, dict):
        return None
    if any(not configuration.get(field) for field in IDENTITY_FIELDS):
        return None
    if not isinstance(configuration["relevant_configuration"], dict):
        return None
    return {field: configuration[field] for field in IDENTITY_FIELDS}


def validate_qualification_inputs(record_path, adapter_configuration_path):
    require_adapter_configuration(read_json(adapter_configuration_path))
    require_cli_provenance(read_json(record_path))


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate-qualification-inputs")
    validate_parser.add_argument("--record", required=True)
    validate_parser.add_argument("--adapter-configuration", required=True)

    args = parser.parse_args()

    try:
        if args.command == "validate-qualification-inputs":
            validate_qualification_inputs(args.record, args.adapter_configuration)
        else:
            raise AssertionError(f"unknown command: {args.command}")
    except (OSError, json.JSONDecodeError, AdapterIdentityError) as exc:
        reason = getattr(exc, "reason", "adapter_configuration_incomplete")
        print(reason)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
