import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from promotion_review import PromotionReviewError, committed_review_revision, validate_review


class PromotionReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "-C", str(self.root), "init", "-q", "-b", "main"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "Axiom Test"], check=True)
        (self.root / "runs" / "run-ok").mkdir(parents=True)
        self.patch_sha = "a" * 64
        self.write_record("run-ok", self.patch_sha)

    def tearDown(self):
        self.tmp.cleanup()

    def write_record(self, run_id, patch_sha):
        record = {
            "run_id": run_id,
            "patch_sha256": patch_sha,
        }
        path = self.root / "runs" / run_id / "record.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record), encoding="utf-8")

    def write_review(self, run_id="run-ok", patch_sha=None, **overrides):
        review = {
            "schema_version": 1,
            "review_type": "promotion",
            "run_id": run_id,
            "patch_sha256": patch_sha or self.patch_sha,
            "reviewer": "reviewer@example.invalid",
            "decision": "APPROVED",
            "concerns": "NO_CONCERNS",
            "follow_up_tasks": [],
        }
        review.update(overrides)
        path = self.root / "reviews" / "promotion" / f"{run_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", str(path.relative_to(self.root))], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-q", "-m", f"review {run_id}"], check=True)

    def assert_reason(self, reason, run_id="run-ok"):
        with self.assertRaises(PromotionReviewError) as caught:
            validate_review(forge_root=self.root, run_dir=self.root / "runs" / run_id)
        self.assertEqual(caught.exception.reason, reason)

    def test_valid_review_returns_committed_revision(self):
        self.write_review()
        result = validate_review(forge_root=self.root, run_dir=self.root / "runs" / "run-ok")
        self.assertEqual(result["path"], "reviews/promotion/run-ok.json")
        self.assertRegex(result["revision"], r"^[0-9a-f]{40}$")

    def test_patch_level_review_can_approve_dynamic_run_id(self):
        dynamic_run_id = "run-dynamic"
        self.write_record(dynamic_run_id, self.patch_sha)
        path = self.root / "reviews" / "promotion" / f"patch-{self.patch_sha}.json"
        review = {
            "schema_version": 1,
            "review_type": "promotion",
            "patch_sha256": self.patch_sha,
            "reviewer": "reviewer@example.invalid",
            "decision": "APPROVED",
            "concerns": "NO_CONCERNS",
            "follow_up_tasks": [],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", str(path.relative_to(self.root))], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-q", "-m", "patch review"], check=True)
        result = validate_review(forge_root=self.root, run_dir=self.root / "runs" / dynamic_run_id)
        self.assertEqual(result["path"], f"reviews/promotion/patch-{self.patch_sha}.json")


    def test_missing_review_fails_closed(self):
        self.assert_reason("missing_promotion_review_result")

    def test_malformed_review_fails_closed(self):
        path = self.root / "reviews" / "promotion" / "run-ok.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not json", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", str(path.relative_to(self.root))], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-q", "-m", "bad review"], check=True)
        self.assert_reason("malformed_promotion_review_result")

    def test_failing_decision_fails_closed(self):
        self.write_review(decision="CHANGES_REQUESTED")
        self.assert_reason("failing_promotion_review_result")

    def test_unresolved_follow_up_fails_closed(self):
        self.write_review(follow_up_tasks=[{"kind": "note", "task_file": "tasks/refactor.task.md"}])
        self.assert_reason("unresolved_promotion_review_followups")

    def test_unresolved_review_revision_fails_closed(self):
        def fake_run_git(_forge_root, *args):
            if args[:2] == ("cat-file", "-e") and str(args[2]).startswith("HEAD:"):
                return subprocess.CompletedProcess(args, 0, "", "")
            if args[:3] == ("log", "-n", "1"):
                return subprocess.CompletedProcess(args, 0, "not-a-sha\n", "")
            return subprocess.CompletedProcess(args, 1, "", "missing")

        with patch("promotion_review.run_git", fake_run_git):
            with self.assertRaises(PromotionReviewError) as caught:
                committed_review_revision(self.root, Path("reviews/promotion/run-ok.json"))
        self.assertEqual(caught.exception.reason, "unresolved_promotion_review_revision")


    def test_patch_mismatch_fails_closed(self):
        self.write_review(patch_sha="b" * 64)
        self.assert_reason("promotion_review_patch_mismatch")


if __name__ == "__main__":
    unittest.main()
