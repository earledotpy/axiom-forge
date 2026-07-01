#!/usr/bin/env python3
import argparse

from compatibility_result import write_result


parser = argparse.ArgumentParser()
parser.add_argument("--file", required=True)
parser.add_argument("--status", required=True, choices=("COMPATIBLE", "INCOMPATIBLE"))
parser.add_argument("--stage", required=True)
parser.add_argument("--failure-reason", default="")
parser.add_argument("--adapter", required=True)
parser.add_argument("--task-file", required=True)
parser.add_argument("--task-source", required=True)
parser.add_argument("--record", required=True)
parser.add_argument("--adapter-script", required=True)
parser.add_argument("--adapter-script-revision", default="")
parser.add_argument("--adapter-configuration", default="")
parser.add_argument("--run-validation", required=True)
parser.add_argument("--patch-verification", required=True)
args = parser.parse_args()

write_result(
    args.file,
    status=args.status,
    stage=args.stage,
    failure_reason=args.failure_reason,
    adapter=args.adapter,
    task_file=args.task_file,
    task_source=args.task_source,
    record_path=args.record,
    adapter_script=args.adapter_script,
    adapter_script_revision=args.adapter_script_revision,
    adapter_configuration_path=args.adapter_configuration,
    run_validation=args.run_validation,
    patch_verification=args.patch_verification,
)
