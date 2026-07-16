import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from forge import promotion


ROOT = Path(__file__).resolve().parents[1]
WRITE_PROMOTION = ROOT / "scripts" / "write_promotion.py"


class PromotionEvidenceTests(unittest.TestCase):
    def test_build_promotion_owns_the_current_promotion_evidence_schema(self):
        record = promotion.build_promotion(
            run_id="run-1",
            status="FAILED",
            reason="stale_base_sha",
            branch="gate/run-1",
            base_sha="a" * 40,
            promotion_commit="",
            target_repo="",
            target_name="",
            target_base_branch="",
            delegation_target_base_sha="",
            target_remote_url="",
            promotion_review_revision="",
        )

        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["run_id"], "run-1")
        self.assertEqual(record["status"], "FAILED")
        self.assertEqual(record["reason"], "stale_base_sha")
        self.assertEqual(record["branch"], "gate/run-1")
        self.assertEqual(record["base_sha"], "a" * 40)
        self.assertIsNone(record["promotion_commit"])
        self.assertIsNone(record["target_repo"])
        self.assertIsNone(record["promotion_review_revision"])
        self.assertTrue(record["timestamp_utc"].endswith("Z"))

    def test_validate_promotion_rejects_a_record_missing_a_schema_field(self):
        record = {"schema_version": 1}

        with self.assertRaises(ValueError):
            promotion.validate_promotion(record)

    def test_write_promotion_cli_preserves_empty_status(self):
        record = self.write_with_cli(status="", reason="")

        self.assertEqual(record["status"], "")
        self.assertIsNone(record["reason"])

    def test_write_promotion_cli_preserves_existing_failure_reasons(self):
        reasons = (
            "target_repo_dirty",
            "target_branch_unavailable",
            "target_not_on_expected_base_branch",
            "target_base_sha_unresolved",
            "default_base_not_found",
            "stale_delegation_target_base",
            "stale_base_sha",
            "invalid_gate_branch_name",
            "gate_branch_already_exists",
            "pre_promotion_verification_failed",
            "unresolved_promotion_review_revision",
            "operator_approval_failed",
            "gate_worktree_create_failed",
            "gate_patch_check_failed",
            "gate_patch_apply_failed",
            "promotion_commit_failed",
            "promotion_commit_lookup_failed",
            "post_promotion_verification_failed",
            "superseded_captured_run",
            "missing_promotion_review_result",
            "malformed_promotion_review_result",
            "failing_promotion_review_result",
            "unresolved_promotion_review_followups",
        )

        for reason in reasons:
            with self.subTest(reason=reason):
                record = self.write_with_cli(status="FAILED", reason=reason)
                self.assertEqual(record["status"], "FAILED")
                self.assertEqual(record["reason"], reason)

    def write_with_cli(self, *, status: str, reason: str) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "promotion.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(WRITE_PROMOTION),
                    "--file",
                    str(path),
                    "--run-id",
                    "run-1",
                    "--status",
                    status,
                    "--reason",
                    reason,
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
