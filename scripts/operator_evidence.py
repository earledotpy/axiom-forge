#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

try:
    from concurrent_task_scopes import (
        ConcurrentTaskScopeError,
        check_concurrent_task_scopes,
    )
    from delegation_artifact_set import load_task_artifact_set
    from promotion_review import PromotionReviewError, validate_review
except ModuleNotFoundError:
    from scripts.concurrent_task_scopes import (
        ConcurrentTaskScopeError,
        check_concurrent_task_scopes,
    )
    from scripts.delegation_artifact_set import load_task_artifact_set
    from scripts.promotion_review import PromotionReviewError, validate_review


SCHEMA_VERSION = 1
STALE_BASE_REASONS = {"stale_base_sha", "stale_delegation_target_base"}
SCOPE_CONFLICT_REASONS = {"concurrent_task_scope_conflict", "patch_outside_target_task_scope"}


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def non_empty_string(record: dict | None, key: str) -> str | None:
    if record is None:
        return None
    value = record.get(key)
    return value if isinstance(value, str) and value else None


def status_record(path: Path, kind: str) -> dict:
    record = load_json(path)
    if record is None:
        return {
            "kind": kind,
            "path": path.as_posix(),
            "status": "MISSING",
            "reason": None,
        }
    return {
        "kind": kind,
        "path": path.as_posix(),
        "status": record.get("status"),
        "reason": record.get("reason"),
    }


def run_drill_down(run_dir: Path) -> dict:
    return {
        "record": (run_dir / "record.json").as_posix(),
        "patch": (run_dir / "patch.diff").as_posix(),
        "verify": (run_dir / "verify.json").as_posix(),
        "post_verify": (run_dir / "post_verify.json").as_posix(),
        "promotion": (run_dir / "promotion.json").as_posix(),
        "adapter_logs": [
            path.as_posix()
            for path in sorted(run_dir.glob("*.log"))
        ],
    }


def summarize_review(forge_root: Path, run_dir: Path, promotion: dict | None, verify: dict | None) -> dict:
    revision = non_empty_string(promotion, "promotion_review_revision")
    if revision is not None:
        return {"status": "APPROVED", "revision": revision, "reason": None}

    promotion_reason = non_empty_string(promotion, "reason")
    if promotion_reason is not None and "promotion_review" in promotion_reason:
        return {"status": "MISSING", "revision": None, "reason": promotion_reason}

    if verify is None or verify.get("status") != "PASS":
        return {"status": "NOT_RUN", "revision": None, "reason": None}

    try:
        result = validate_review(forge_root=forge_root, run_dir=run_dir)
    except PromotionReviewError as exc:
        return {"status": "MISSING", "revision": None, "reason": exc.reason}
    return {"status": "APPROVED", "revision": result["revision"], "reason": None}


def promotion_state(record: dict | None, verify: dict | None, review: dict, promotion: dict | None) -> str:
    if promotion is not None and promotion.get("status") == "PROMOTED":
        return "promoted"
    if non_empty_string(record, "superseded_by_run_id") is not None:
        return "superseded"
    if record is not None and record.get("failure_class") == "adapter_availability":
        return "availability-failure"
    if record is not None and record.get("run_status") == "FAILED":
        return "failed"
    if verify is not None and verify.get("status") == "PASS" and review.get("status") == "APPROVED":
        return "promotion-ready"
    if verify is not None and verify.get("status") == "PASS":
        return "verified"
    if record is not None and record.get("run_status") == "COMPLETED":
        return "captured"
    return "failed"


def summarize_run(run_dir: Path, forge_root: Path | None = None) -> dict:
    run_dir = Path(run_dir)
    forge_root = Path.cwd() if forge_root is None else Path(forge_root)
    record = load_json(run_dir / "record.json")
    verify = load_json(run_dir / "verify.json")
    post_verify = load_json(run_dir / "post_verify.json")
    promotion = load_json(run_dir / "promotion.json")
    review = summarize_review(forge_root, run_dir, promotion, verify)

    promotion_reason = non_empty_string(promotion, "reason")
    verify_reason = non_empty_string(verify, "reason")
    state = promotion_state(record, verify, review, promotion)

    return {
        "schema_version": SCHEMA_VERSION,
        "source": "run",
        "state": state,
        "run": {
            "run_id": non_empty_string(record, "run_id") or run_dir.name,
            "run_mode": non_empty_string(record, "run_mode") or "forge-local",
            "adapter": non_empty_string(record, "agent"),
            "status": non_empty_string(record, "run_status"),
            "failure_reason": non_empty_string(record, "failure_reason"),
            "failure_class": non_empty_string(record, "failure_class"),
            "superseded_by_run_id": non_empty_string(record, "superseded_by_run_id"),
            "superseded_reason": non_empty_string(record, "superseded_reason"),
        },
        "task": {
            "task_file": non_empty_string(record, "delegation_task_file")
            or non_empty_string(record, "task_file"),
            "approved_scope_file": non_empty_string(record, "target_scope_file"),
            "approved_scope_sha256": non_empty_string(record, "target_scope_sha256"),
        },
        "patch": {
            "state": "present" if (run_dir / "patch.diff").exists() else "missing",
            "path": (run_dir / "patch.diff").as_posix(),
            "sha256": non_empty_string(record, "patch_sha256"),
        },
        "verification": status_record(run_dir / "verify.json", "verification"),
        "post_promotion_verification": status_record(run_dir / "post_verify.json", "post_promotion_verification"),
        "promotion_review": review,
        "promotion": {
            "status": non_empty_string(promotion, "status"),
            "reason": promotion_reason,
            "branch": non_empty_string(promotion, "branch"),
            "promotion_commit": non_empty_string(promotion, "promotion_commit"),
        },
        "target": {
            "name": non_empty_string(record, "target_name"),
            "repo": non_empty_string(record, "target_repo"),
            "base_branch": non_empty_string(record, "target_base_branch"),
            "target_base_sha": non_empty_string(record, "target_base_sha"),
            "delegation_target_base_sha": non_empty_string(record, "delegation_target_base_sha"),
            "stale_base": promotion_reason in STALE_BASE_REASONS,
        },
        "scope": {
            "conflict": promotion_reason in SCOPE_CONFLICT_REASONS or verify_reason in SCOPE_CONFLICT_REASONS,
            "reason": promotion_reason if promotion_reason in SCOPE_CONFLICT_REASONS else verify_reason,
        },
        "evidence_revisions": {
            "delegation_artifact_revision": non_empty_string(record, "delegation_artifact_revision"),
            "delegation_target_base_sha": non_empty_string(record, "delegation_target_base_sha"),
            "promotion_review_revision": review.get("revision"),
        },
        "drill_down": run_drill_down(run_dir),
    }


def summarize_runs(runs_root: Path, forge_root: Path | None = None) -> dict:
    runs_root = Path(runs_root)
    run_summaries = [
        summarize_run(record_path.parent, forge_root)
        for record_path in sorted(runs_root.glob("*/record.json"))
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "source": "run-history",
        "state": "captured" if run_summaries else "empty",
        "runs_root": runs_root.as_posix(),
        "runs": run_summaries,
    }


def summarize_task(task_file: Path) -> dict:
    task_file = Path(task_file)
    task = load_task_artifact_set(task_file)
    is_ready = task.state == "delegation-ready"
    return {
        "schema_version": SCHEMA_VERSION,
        "source": "task",
        "state": task.state,
        "task": {
            "task_file": task_file.as_posix(),
            "approved_scope_file": task.scope_file if is_ready else None,
            "acceptance_file": task.acceptance_file if is_ready else None,
            "approved_paths": sorted(task.approved_paths) if is_ready else [],
        },
        "scope": {"conflict": False, "reason": None, "conflicts": []},
    }


def summarize_tasks(task_files: list[Path]) -> dict:
    summaries = [summarize_task(task_file) for task_file in task_files]
    conflicts = []
    reason = None
    try:
        check_concurrent_task_scopes(task_files)
    except ConcurrentTaskScopeError as exc:
        reason = exc.reason
        conflicts = [
            {
                "first_task_file": conflict.first_task_file,
                "second_task_file": conflict.second_task_file,
                "overlapping_paths": list(conflict.overlapping_paths),
            }
            for conflict in exc.conflicts
        ]

    return {
        "schema_version": SCHEMA_VERSION,
        "source": "task-set",
        "state": "scope-conflict" if conflicts else "delegation-ready",
        "scope": {
            "conflict": bool(conflicts),
            "reason": reason,
            "conflicts": conflicts,
        },
        "tasks": summaries,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("run_dir")
    run_parser.add_argument("--forge-root", default=".")

    runs_parser = subparsers.add_parser("runs")
    runs_parser.add_argument("runs_root")
    runs_parser.add_argument("--forge-root", default=".")

    task_parser = subparsers.add_parser("task")
    task_parser.add_argument("task_file")

    tasks_parser = subparsers.add_parser("tasks")
    tasks_parser.add_argument("task_files", nargs="+")

    args = parser.parse_args(argv)
    if args.command == "run":
        summary = summarize_run(Path(args.run_dir), Path(args.forge_root).resolve())
    elif args.command == "runs":
        summary = summarize_runs(Path(args.runs_root), Path(args.forge_root).resolve())
    elif args.command == "task":
        summary = summarize_task(Path(args.task_file))
    elif args.command == "tasks":
        summary = summarize_tasks([Path(path) for path in args.task_files])
    else:
        raise AssertionError(f"unknown command: {args.command}")

    try:
        print(json.dumps(summary, indent=2) + "\n", end="")
    except BrokenPipeError:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
