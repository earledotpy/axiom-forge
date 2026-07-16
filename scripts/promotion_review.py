#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forge.git import run_git


REVIEW_DIR = PurePosixPath("reviews/promotion")
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PATCH_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")


class PromotionReviewError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason



def load_json(path: Path, reason: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raise PromotionReviewError(reason)
    if not isinstance(value, dict):
        raise PromotionReviewError(reason)
    return value


def require_string(record: dict, key: str, reason: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise PromotionReviewError(reason)
    return value


def review_path_for_run(run_id: str) -> PurePosixPath:
    if not RUN_ID_RE.fullmatch(run_id):
        raise PromotionReviewError("malformed_promotion_review_result")
    return REVIEW_DIR / f"{run_id}.json"


def review_path_for_patch(patch_sha256: str) -> PurePosixPath:
    if not PATCH_SHA_RE.fullmatch(patch_sha256):
        raise PromotionReviewError("malformed_promotion_review_result")
    return REVIEW_DIR / f"patch-{patch_sha256}.json"


def committed_review_revision(forge_root: Path, review_path: PurePosixPath) -> str:
    path = str(review_path)
    tracked = run_git(forge_root, "cat-file", "-e", f"HEAD:{path}")
    if tracked.returncode != 0:
        raise PromotionReviewError("missing_promotion_review_result")

    revision = run_git(forge_root, "log", "-n", "1", "--format=%H", "HEAD", "--", path)
    if revision.returncode != 0:
        raise PromotionReviewError("unresolved_promotion_review_revision")
    value = revision.stdout.strip()
    if not FULL_SHA_RE.fullmatch(value):
        raise PromotionReviewError("unresolved_promotion_review_revision")

    exists = run_git(forge_root, "cat-file", "-e", f"{value}^{{commit}}")
    if exists.returncode != 0:
        raise PromotionReviewError("unresolved_promotion_review_revision")
    return value


def load_committed_review(forge_root: Path, revision: str, review_path: PurePosixPath) -> dict:
    shown = run_git(forge_root, "show", f"{revision}:{review_path}")
    if shown.returncode != 0:
        raise PromotionReviewError("missing_promotion_review_result")
    try:
        value = json.loads(shown.stdout)
    except Exception:
        raise PromotionReviewError("malformed_promotion_review_result")
    if not isinstance(value, dict):
        raise PromotionReviewError("malformed_promotion_review_result")
    return value


def validate_follow_up_tasks(review: dict) -> None:
    tasks = review.get("follow_up_tasks")
    if tasks is None:
        raise PromotionReviewError("malformed_promotion_review_result")
    if not isinstance(tasks, list):
        raise PromotionReviewError("malformed_promotion_review_result")
    for task in tasks:
        if not isinstance(task, dict):
            raise PromotionReviewError("unresolved_promotion_review_followups")
        kind = task.get("kind")
        task_file = task.get("task_file")
        if kind != "bounded_patch_task" or not isinstance(task_file, str):
            raise PromotionReviewError("unresolved_promotion_review_followups")
        pure = PurePosixPath(task_file)
        if (
            "\\" in task_file
            or pure.is_absolute()
            or not task_file.startswith("tasks/")
            or not task_file.endswith(".task.md")
            or any(part in ("", ".", "..") for part in pure.parts)
        ):
            raise PromotionReviewError("unresolved_promotion_review_followups")


def find_committed_review(forge_root: Path, run_id: str, patch_sha256: str) -> tuple[PurePosixPath, str, dict]:
    for candidate in (review_path_for_run(run_id), review_path_for_patch(patch_sha256)):
        try:
            revision = committed_review_revision(forge_root, candidate)
        except PromotionReviewError as exc:
            if exc.reason == "missing_promotion_review_result":
                continue
            raise
        return candidate, revision, load_committed_review(forge_root, revision, candidate)
    raise PromotionReviewError("missing_promotion_review_result")


def validate_review(*, forge_root: Path, run_dir: Path) -> dict:
    record = load_json(run_dir / "record.json", "missing_record_json")
    run_id = require_string(record, "run_id", "missing_run_id")
    patch_sha256 = require_string(record, "patch_sha256", "missing_patch_sha256")

    review_path, revision, review = find_committed_review(forge_root, run_id, patch_sha256)

    if review.get("schema_version") != 1:
        raise PromotionReviewError("malformed_promotion_review_result")
    if review.get("review_type") != "promotion":
        raise PromotionReviewError("malformed_promotion_review_result")
    reviewed_run_id = review.get("run_id")
    if reviewed_run_id is not None and reviewed_run_id != run_id:
        raise PromotionReviewError("promotion_review_run_mismatch")
    if review.get("patch_sha256") != patch_sha256:
        raise PromotionReviewError("promotion_review_patch_mismatch")

    reviewer = review.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer:
        raise PromotionReviewError("malformed_promotion_review_result")
    decision = review.get("decision")
    if decision != "APPROVED":
        raise PromotionReviewError("failing_promotion_review_result")
    concerns = review.get("concerns")
    if not isinstance(concerns, str) or not concerns:
        raise PromotionReviewError("malformed_promotion_review_result")

    validate_follow_up_tasks(review)
    return {"path": str(review_path), "revision": revision}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--forge-root", required=True)
    validate_parser.add_argument("--run-dir", required=True)

    args = parser.parse_args(argv)
    if args.command == "validate":
        try:
            result = validate_review(
                forge_root=Path(args.forge_root).resolve(),
                run_dir=Path(args.run_dir),
            )
        except PromotionReviewError as exc:
            print(exc.reason)
            return 1
        print(f"promotion_review_file={result['path']}")
        print(f"promotion_review_revision={result['revision']}")
        return 0

    raise AssertionError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
