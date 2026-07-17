import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import (
    adapter_identity,
    compatibility_result,
    operator_evidence,
    promotion_review,
    qualification_result,
    target_preflight,
    target_verify,
)


class SmallHelperSeamTests(unittest.TestCase):
    def test_optional_json_read_keeps_missing_and_valid_file_behavior(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            valid = root / "valid.json"
            valid.write_text(json.dumps({"answer": 42}), encoding="utf-8")

            self.assertIsNone(adapter_identity.read_json(root / "missing.json"))
            self.assertEqual(adapter_identity.read_json(valid), {"answer": 42})

    def test_promotion_review_malformed_json_keeps_caller_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "record.json"
            path.write_text("not json", encoding="utf-8")

            with self.assertRaises(promotion_review.PromotionReviewError) as caught:
                promotion_review.load_json(path, "missing_record_json")

        self.assertEqual(caught.exception.reason, "missing_record_json")

    def test_target_preflight_blank_required_value_keeps_caller_reason(self):
        with self.assertRaises(target_preflight.PreflightFailure) as caught:
            target_preflight.require_string({"name": "   "}, "name")

        self.assertEqual(caught.exception.reason, "target_config_malformed")

    def test_target_verify_missing_required_value_keeps_caller_reason(self):
        with self.assertRaises(target_verify.TargetVerifyFailure) as caught:
            target_verify.require_string({}, "run_id", "missing_run_id")

        self.assertEqual(caught.exception.reason, "missing_run_id")

    def test_optional_json_callers_keep_malformed_json_behavior(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "malformed.json"
            path.write_text("not json", encoding="utf-8")

            for read_json in (
                adapter_identity.read_json,
                compatibility_result.read_json,
                qualification_result.read_json,
            ):
                with self.assertRaises(json.JSONDecodeError):
                    read_json(path)

            self.assertIsNone(operator_evidence.load_json(path))

    def test_target_verify_malformed_record_keeps_caller_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "record.json"
            path.write_text("not json", encoding="utf-8")

            with self.assertRaises(target_verify.TargetVerifyFailure) as caught:
                target_verify.load_record(path)

        self.assertEqual(caught.exception.reason, "target_record_malformed")

    def test_sha256_entry_point_keeps_digest_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "payload.txt"
            path.write_bytes(b"Axiom Forge\n")

            completed = subprocess.run(
                [sys.executable, "scripts/sha256_file.py", str(path)],
                check=True,
                capture_output=True,
                text=True,
            )

        self.assertEqual(
            completed.stdout.strip(),
            hashlib.sha256(b"Axiom Forge\n").hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
