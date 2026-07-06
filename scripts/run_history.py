#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

try:
    from run_record import RunRecordError, is_safe_run_id, supersession_reason
except ModuleNotFoundError:
    from scripts.run_record import RunRecordError, is_safe_run_id, supersession_reason


def load_record(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_record(path, record):
    Path(path).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def _non_empty_string(record, key):
    value = record.get(key)
    return value if isinstance(value, str) and value else None


def supersession_candidate_reason(previous, current):
    if previous.get("run_mode", "forge-local") != "target":
        return None
    if current.get("run_mode", "forge-local") != "target":
        return None

    previous_task = _non_empty_string(previous, "delegation_task_file")
    current_task = _non_empty_string(current, "delegation_task_file")
    if previous_task is None or previous_task != current_task:
        return None

    previous_base = _non_empty_string(previous, "delegation_target_base_sha")
    current_base = _non_empty_string(current, "delegation_target_base_sha")
    if previous_base is not None and current_base is not None and previous_base != current_base:
        return "newer_delegation_target_base"

    previous_revision = _non_empty_string(previous, "delegation_artifact_revision")
    current_revision = _non_empty_string(current, "delegation_artifact_revision")
    if previous_revision is not None and current_revision is not None and previous_revision != current_revision:
        return "replacement_delegation_artifact_set"

    return None


def mark_superseded_runs(runs_root, current_record_path):
    current_record_path = Path(current_record_path)
    runs_root = Path(runs_root)
    current = load_record(current_record_path)
    current_run_id = _non_empty_string(current, "run_id")
    if current_run_id is None or not is_safe_run_id(current_run_id):
        raise RunRecordError("missing_run_id")

    marked = []
    for record_path in sorted(runs_root.glob("*/record.json")):
        if record_path.resolve() == current_record_path.resolve():
            continue

        try:
            previous = load_record(record_path)
        except (OSError, json.JSONDecodeError):
            continue

        previous_run_id = _non_empty_string(previous, "run_id")
        if previous_run_id is None or previous_run_id >= current_run_id:
            continue

        reason = supersession_candidate_reason(previous, current)
        if reason is None:
            continue

        previous["superseded_by_run_id"] = current_run_id
        previous["superseded_reason"] = reason
        write_record(record_path, previous)
        marked.append(previous_run_id)

    return marked


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    mark_parser = subparsers.add_parser("mark-superseded")
    mark_parser.add_argument("--runs-root", required=True)
    mark_parser.add_argument("--current-record", required=True)

    check_parser = subparsers.add_parser("check-promotable")
    check_parser.add_argument("--record", required=True)

    args = parser.parse_args()

    if args.command == "mark-superseded":
        try:
            for run_id in mark_superseded_runs(args.runs_root, args.current_record):
                print(run_id)
        except (OSError, json.JSONDecodeError, RunRecordError) as exc:
            print(getattr(exc, "reason", "run_history_update_failed"))
            return 1
        return 0

    if args.command == "check-promotable":
        try:
            record = load_record(args.record)
            if supersession_reason(record) is not None:
                print("superseded_captured_run")
                return 1
        except (OSError, json.JSONDecodeError):
            print("missing_run_id")
            return 1
        except RunRecordError as exc:
            print(exc.reason)
            return 1
        return 0

    raise AssertionError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())