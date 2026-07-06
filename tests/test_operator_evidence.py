import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import operator_evidence


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def base_record(**overrides):
    record = {
        "schema_version": 2,
        "run_id": "run-1",
        "agent": "manual-simulated-agent",
        "run_mode": "target",
        "run_status": "COMPLETED",
        "failure_reason": None,
        "failure_class": None,
        "base_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "patch_file": "patch.diff",
        "patch_sha256": "b" * 64,
        "target_name": "test-target",
        "target_repo": "/tmp/target",
        "target_base_branch": "main",
        "target_base_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "target_scope_file": "allowed-paths.txt",
        "target_scope_sha256": "scope-hash",
        "delegation_artifact_revision": "c" * 40,
        "delegation_target_base_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "delegation_task_file": "tasks/change-answer.task.md",
    }
    record.update(overrides)
    return record


class OperatorEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write_run(self, run_id="run-1", *, record=None, verify=None, promotion=None):
        run_dir = self.root / "runs" / run_id
        run_dir.mkdir(parents=True)
        write_json(run_dir / "record.json", record or base_record(run_id=run_id))
        (run_dir / "patch.diff").write_text("diff --git a/app.py b/app.py\n", encoding="utf-8")
        if verify is not None:
            write_json(run_dir / "verify.json", verify)
        if promotion is not None:
            write_json(run_dir / "promotion.json", promotion)
        return run_dir

    def test_draft_task_summary_does_not_require_raw_logs(self):
        task = self.root / "tasks" / "draft.task.md"
        task.parent.mkdir()
        task.write_text("# Draft\n", encoding="utf-8")

        summary = operator_evidence.summarize_task(task)

        self.assertEqual(summary["state"], "draft")
        self.assertEqual(summary["task"]["task_file"], task.as_posix())
        self.assertFalse(summary["scope"]["conflict"])

    def test_delegation_ready_task_summary_includes_approved_scope(self):
        task = self.root / "tasks" / "ready.task.md"
        task.parent.mkdir()
        task.write_text("# Ready\n", encoding="utf-8")
        (self.root / "tasks" / "ready.allowed-paths.txt").write_text("app/target.py\n", encoding="utf-8")
        (self.root / "tasks" / "ready.accept.sh").write_text("echo ok\n", encoding="utf-8")

        summary = operator_evidence.summarize_task(task)

        self.assertEqual(summary["state"], "delegation-ready")
        self.assertEqual(summary["task"]["approved_paths"], ["app/target.py"])
        self.assertEqual(summary["task"]["acceptance_file"], (self.root / "tasks" / "ready.accept.sh").as_posix())

    def test_scope_conflict_summary_is_structured(self):
        first = self.root / "tasks" / "first.task.md"
        second = self.root / "tasks" / "second.task.md"
        first.parent.mkdir()
        for task, name in ((first, "first"), (second, "second")):
            task.write_text(f"# {name}\n", encoding="utf-8")
            (self.root / "tasks" / f"{name}.allowed-paths.txt").write_text("app/target.py\n", encoding="utf-8")
            (self.root / "tasks" / f"{name}.accept.sh").write_text("echo ok\n", encoding="utf-8")

        summary = operator_evidence.summarize_tasks([first, second])

        self.assertEqual(summary["state"], "scope-conflict")
        self.assertTrue(summary["scope"]["conflict"])
        self.assertEqual(summary["scope"]["reason"], "concurrent_task_scope_conflict")
        self.assertEqual(summary["scope"]["conflicts"][0]["overlapping_paths"], ["app/target.py"])

    def test_captured_run_summary(self):
        run_dir = self.write_run()

        summary = operator_evidence.summarize_run(run_dir, self.root)

        self.assertEqual(summary["state"], "captured")
        self.assertEqual(summary["run"]["adapter"], "manual-simulated-agent")
        self.assertEqual(summary["evidence_revisions"]["delegation_artifact_revision"], "c" * 40)
        self.assertIn("adapter_logs", summary["drill_down"])

    def test_verified_not_promotion_ready_summary(self):
        run_dir = self.write_run(verify={"schema_version": 1, "status": "PASS"})

        with patch("scripts.operator_evidence.validate_review") as validate:
            validate.side_effect = operator_evidence.PromotionReviewError("missing_promotion_review_result")
            summary = operator_evidence.summarize_run(run_dir, self.root)

        self.assertEqual(summary["state"], "verified")
        self.assertEqual(summary["verification"]["status"], "PASS")
        self.assertEqual(summary["promotion_review"]["status"], "MISSING")
        self.assertEqual(summary["promotion_review"]["reason"], "missing_promotion_review_result")

    def test_promotion_ready_summary(self):
        run_dir = self.write_run(verify={"schema_version": 1, "status": "PASS"})

        with patch("scripts.operator_evidence.validate_review") as validate:
            validate.return_value = {"revision": "d" * 40}
            summary = operator_evidence.summarize_run(run_dir, self.root)

        self.assertEqual(summary["state"], "promotion-ready")
        self.assertEqual(summary["promotion_review"]["status"], "APPROVED")
        self.assertEqual(summary["evidence_revisions"]["promotion_review_revision"], "d" * 40)

    def test_promoted_summary_includes_promotion_evidence(self):
        run_dir = self.write_run(
            verify={"schema_version": 1, "status": "PASS"},
            promotion={
                "schema_version": 1,
                "run_id": "run-1",
                "status": "PROMOTED",
                "branch": "gate/run-1",
                "promotion_commit": "e" * 40,
                "promotion_review_revision": "f" * 40,
            },
        )

        summary = operator_evidence.summarize_run(run_dir, self.root)

        self.assertEqual(summary["state"], "promoted")
        self.assertEqual(summary["promotion"]["branch"], "gate/run-1")
        self.assertEqual(summary["promotion"]["promotion_commit"], "e" * 40)

    def test_failed_run_summary(self):
        run_dir = self.write_run(
            record=base_record(
                run_status="FAILED",
                failure_reason="agent_execution_failed",
                failure_class="task_incorrect",
            )
        )

        summary = operator_evidence.summarize_run(run_dir, self.root)

        self.assertEqual(summary["state"], "failed")
        self.assertEqual(summary["run"]["failure_reason"], "agent_execution_failed")
        self.assertEqual(summary["run"]["failure_class"], "task_incorrect")

    def test_availability_failure_summary(self):
        run_dir = self.write_run(
            record=base_record(
                run_status="FAILED",
                failure_reason="adapter_quota_exhausted",
                failure_class="adapter_availability",
            )
        )

        summary = operator_evidence.summarize_run(run_dir, self.root)

        self.assertEqual(summary["state"], "availability-failure")
        self.assertEqual(summary["run"]["failure_reason"], "adapter_quota_exhausted")

    def test_superseded_summary(self):
        run_dir = self.write_run(
            record=base_record(
                superseded_by_run_id="run-2",
                superseded_reason="newer_delegation_target_base",
            )
        )

        summary = operator_evidence.summarize_run(run_dir, self.root)

        self.assertEqual(summary["state"], "superseded")
        self.assertEqual(summary["run"]["superseded_by_run_id"], "run-2")
        self.assertEqual(summary["run"]["superseded_reason"], "newer_delegation_target_base")

    def test_run_history_summary_lists_captured_runs(self):
        first = self.write_run("run-1")
        second = self.write_run(
            "run-2",
            record=base_record(
                run_id="run-2",
                run_status="FAILED",
                failure_reason="adapter_cli_unavailable",
                failure_class="adapter_availability",
            ),
        )

        summary = operator_evidence.summarize_runs(self.root / "runs", self.root)

        self.assertEqual(summary["source"], "run-history")
        self.assertEqual([run["run"]["run_id"] for run in summary["runs"]], ["run-1", "run-2"])
        self.assertEqual(summary["runs"][0]["drill_down"]["record"], (first / "record.json").as_posix())
        self.assertEqual(summary["runs"][1]["state"], "availability-failure")
        self.assertEqual(summary["runs"][1]["drill_down"]["record"], (second / "record.json").as_posix())

    def test_stale_base_status_is_visible(self):
        run_dir = self.write_run(
            verify={"schema_version": 1, "status": "PASS"},
            promotion={
                "schema_version": 1,
                "run_id": "run-1",
                "status": "FAILED",
                "reason": "stale_delegation_target_base",
            },
        )

        summary = operator_evidence.summarize_run(run_dir, self.root)

        self.assertEqual(summary["state"], "verified")
        self.assertTrue(summary["target"]["stale_base"])
        self.assertEqual(summary["promotion"]["reason"], "stale_delegation_target_base")


if __name__ == "__main__":
    unittest.main()
