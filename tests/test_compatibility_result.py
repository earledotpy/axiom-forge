import json
import tempfile
import unittest
from pathlib import Path

from scripts import compatibility_result


class CompatibilityResultTests(unittest.TestCase):
    def test_result_is_explicitly_not_standard_trust_or_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = root / "tasks" / "change-answer.task.md"
            task.parent.mkdir()
            task.write_text("Change answer\n", encoding="utf-8")
            run_dir = root / "runs" / "run-1"
            run_dir.mkdir(parents=True)
            record = {
                "run_id": "run-1",
                "base_sha": "abc123",
                "patch_sha256": "patch-hash",
                "run_status": "COMPLETED",
                "failure_reason": None,
                "cli_command": "python",
                "cli_path": "/fixture/python",
                "cli_version": "Python 3",
            }
            record_path = run_dir / "record.json"
            record_path.write_text(json.dumps(record), encoding="utf-8")

            result = compatibility_result.build_result(
                status="COMPATIBLE",
                stage="complete",
                failure_reason="",
                adapter="manual-simulated-agent",
                task_file="tasks/change-answer.task.md",
                task_source=task,
                record_path=record_path,
                adapter_script="agents/manual-simulated-agent.sh",
                adapter_script_revision="rev-1",
                adapter_configuration_path="",
                run_validation="PASSED",
                patch_verification="PASSED",
            )

        self.assertEqual(result["result_type"], "candidate_adapter_compatibility")
        self.assertEqual(result["status"], "COMPATIBLE")
        self.assertEqual(result["compatibility_decision"], "COMPATIBLE")
        self.assertEqual(result["standard_trust_decision"], "NOT_STANDARD_TRUST")
        self.assertEqual(result["promotion_decision"], "NOT_PROMOTION_APPROVAL")
        self.assertEqual(result["adapter_configuration"]["cli_command"], "python")
        self.assertTrue(result["task"]["sha256"])

    def test_failed_result_preserves_stable_failure_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = root / "tasks" / "change-answer.task.md"
            task.parent.mkdir()
            task.write_text("Change answer\n", encoding="utf-8")
            run_dir = root / "runs" / "run-1"
            run_dir.mkdir(parents=True)
            record_path = run_dir / "record.json"
            record_path.write_text(
                json.dumps(
                    {
                        "run_id": "run-1",
                        "base_sha": "abc123",
                        "patch_sha256": "",
                        "run_status": "FAILED",
                        "failure_reason": "agent_produced_empty_patch",
                        "cli_command": "python",
                        "cli_path": "/fixture/python",
                        "cli_version": "Python 3",
                    }
                ),
                encoding="utf-8",
            )

            result = compatibility_result.build_result(
                status="INCOMPATIBLE",
                stage="run_capture",
                failure_reason="agent_produced_empty_patch",
                adapter="bad-empty-agent",
                task_file="tasks/change-answer.task.md",
                task_source=task,
                record_path=record_path,
                adapter_script="agents/bad-empty-agent.sh",
                adapter_script_revision="rev-1",
                adapter_configuration_path="",
                run_validation="NOT_RUN",
                patch_verification="NOT_RUN",
            )

        self.assertEqual(result["status"], "INCOMPATIBLE")
        self.assertEqual(result["failure_reason"], "agent_produced_empty_patch")
        self.assertEqual(result["run_failure_reason"], "agent_produced_empty_patch")
        self.assertEqual(result["compatibility_decision"], "INCOMPATIBLE")


if __name__ == "__main__":
    unittest.main()
