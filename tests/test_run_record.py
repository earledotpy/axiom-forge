import json
import tempfile
import unittest
from pathlib import Path

from scripts import run_record


class RunRecordTests(unittest.TestCase):
    def test_write_record_uses_strict_schema_and_current_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "record.json"

            run_record.write_record(
                path,
                run_id="run-1",
                agent="agent",
                base_sha="abc123",
                status="COMPLETED",
                task_file="task.md",
                patch_file="patch.diff",
                patch_sha256="hash",
                failure_reason="",
                cli_command="python",
                cli_path="/bin/python",
                cli_version="Python 3",
            )

            record = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(record["schema_version"], 2)
        self.assertEqual(record["run_id"], "run-1")
        self.assertEqual(record["target_repo"], ".")
        self.assertEqual(record["patch_sha256"], "hash")
        self.assertIsNone(record["failure_reason"])
        self.assertEqual(record["cli_command"], "python")
        self.assertIn("timestamp_utc", record)

    def test_completed_validation_accepts_older_record_shape(self):
        record = {
            "schema_version": 1,
            "run_id": "old-run",
            "agent": "agent",
            "target_repo": ".",
            "base_sha": "abc123",
            "patch_file": "patch.diff",
            "run_status": "COMPLETED",
        }

        validated = run_record.validate_completed_record(
            record,
            run_dir_name="old-run",
            patch_sha256_actual="actual",
        )

        self.assertEqual(validated["run_id"], "old-run")
        self.assertEqual(validated["base_sha"], "abc123")

    def test_patch_hash_mismatch_fails_completed_validation(self):
        record = {
            "run_id": "run-1",
            "base_sha": "abc123",
            "run_status": "COMPLETED",
            "patch_sha256": "expected",
        }

        with self.assertRaises(run_record.RunRecordError) as caught:
            run_record.validate_completed_record(
                record,
                run_dir_name="run-1",
                patch_sha256_actual="actual",
            )

        self.assertEqual(caught.exception.reason, "patch_sha256_mismatch")

    def test_run_id_directory_mismatch_fails_completed_validation(self):
        record = {
            "run_id": "record-run",
            "base_sha": "abc123",
            "run_status": "COMPLETED",
        }

        with self.assertRaises(run_record.RunRecordError) as caught:
            run_record.validate_completed_record(record, run_dir_name="dir-run")

        self.assertEqual(caught.exception.reason, "run_id_directory_mismatch")

    def test_non_completed_record_fails_completed_validation(self):
        record = {
            "run_id": "run-1",
            "base_sha": "abc123",
            "run_status": "FAILED",
        }

        with self.assertRaises(run_record.RunRecordError) as caught:
            run_record.validate_completed_record(record, run_dir_name="run-1")

        self.assertEqual(caught.exception.reason, "run_not_completed")


    def test_failed_target_record_can_omit_unproven_target_identity(self):
        record = run_record.build_record(
            run_id="target-fail",
            agent="agent",
            base_sha="",
            status="FAILED",
            run_mode="target",
            target_repo="",
            failure_reason="target_remote_mismatch",
        )

        self.assertEqual(record["run_mode"], "target")
        self.assertEqual(record["base_sha"], "")
        self.assertIsNone(record["target_repo"])
        self.assertIsNone(record["target_name"])
        self.assertEqual(record["failure_reason"], "target_remote_mismatch")

        with self.assertRaises(run_record.RunRecordError) as caught:
            run_record.validate_completed_record(record, run_dir_name="target-fail")

        self.assertEqual(caught.exception.reason, "run_not_completed")

    def test_target_mode_validation_requires_target_identity_fields(self):
        record = {
            "run_id": "target-run",
            "base_sha": "abc123",
            "run_status": "COMPLETED",
            "run_mode": "target",
            "target_repo": "/tmp/target",
            "target_base_branch": "main",
            "target_base_sha": "abc123",
            "target_remote_url": "https://example.test/target.git",
        }

        with self.assertRaises(run_record.RunRecordError) as caught:
            run_record.validate_completed_record(record, run_dir_name="target-run")

        self.assertEqual(caught.exception.reason, "missing_target_name")

    def test_target_mode_validation_accepts_target_identity_fields(self):
        record = {
            "run_id": "target-run",
            "base_sha": "abc123",
            "run_status": "COMPLETED",
            "run_mode": "target",
            "target_name": "axiom",
            "target_repo": "/tmp/target",
            "target_base_branch": "main",
            "target_base_sha": "abc123",
            "target_remote_url": "https://example.test/target.git",
            "target_scope_file": "allowed-paths.txt",
            "target_scope_sha256": "scope-hash",
        }

        validated = run_record.validate_completed_record(record, run_dir_name="target-run")

        self.assertEqual(validated["base_sha"], "abc123")


    def test_target_mode_validation_requires_scope_fields(self):
        record = {
            "run_id": "target-run",
            "base_sha": "abc123",
            "run_status": "COMPLETED",
            "run_mode": "target",
            "target_name": "axiom",
            "target_repo": "/tmp/target",
            "target_base_branch": "main",
            "target_base_sha": "abc123",
            "target_remote_url": "https://example.test/target.git",
        }

        with self.assertRaises(run_record.RunRecordError) as caught:
            run_record.validate_completed_record(record, run_dir_name="target-run")

        self.assertEqual(caught.exception.reason, "missing_target_scope_file")

    def test_target_mode_validation_rejects_scope_hash_mismatch(self):
        record = {
            "run_id": "target-run",
            "base_sha": "abc123",
            "run_status": "COMPLETED",
            "run_mode": "target",
            "target_name": "axiom",
            "target_repo": "/tmp/target",
            "target_base_branch": "main",
            "target_base_sha": "abc123",
            "target_remote_url": "https://example.test/target.git",
            "target_scope_file": "allowed-paths.txt",
            "target_scope_sha256": "expected",
        }

        with self.assertRaises(run_record.RunRecordError) as caught:
            run_record.validate_completed_record(
                record,
                run_dir_name="target-run",
                target_scope_sha256_actual="actual",
            )

        self.assertEqual(caught.exception.reason, "target_scope_sha256_mismatch")

    def test_forge_local_validation_does_not_require_scope_fields(self):
        record = {
            "run_id": "forge-run",
            "base_sha": "abc123",
            "run_status": "COMPLETED",
            "run_mode": "forge-local",
        }

        validated = run_record.validate_completed_record(record, run_dir_name="forge-run")

        self.assertEqual(validated["base_sha"], "abc123")

if __name__ == "__main__":
    unittest.main()
