import json
import tempfile
import unittest
from pathlib import Path

from scripts import run_history


def write_record(path, **overrides):
    record = {
        "schema_version": 2,
        "run_id": path.parent.name,
        "agent": "agent",
        "run_mode": "target",
        "delegation_task_file": "tasks/change-answer.task.md",
        "delegation_artifact_revision": "1111111111111111111111111111111111111111",
        "delegation_target_base_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "base_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "run_status": "COMPLETED",
        "failure_reason": None,
    }
    record.update(overrides)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


class RunHistoryTests(unittest.TestCase):
    def test_newer_target_base_marks_older_run_superseded(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp)
            old_record = runs / "20260706-010000-000000" / "record.json"
            new_record = runs / "20260706-020000-000000" / "record.json"
            write_record(old_record)
            write_record(
                new_record,
                run_id="20260706-020000-000000",
                delegation_target_base_sha="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                base_sha="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            )

            marked = run_history.mark_superseded_runs(runs, new_record)
            old = json.loads(old_record.read_text(encoding="utf-8"))

        self.assertEqual(marked, ["20260706-010000-000000"])
        self.assertEqual(old["superseded_by_run_id"], "20260706-020000-000000")
        self.assertEqual(old["superseded_reason"], "newer_delegation_target_base")

    def test_replacement_delegation_artifact_marks_failed_run_superseded(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp)
            old_record = runs / "20260706-010000-000000" / "record.json"
            new_record = runs / "20260706-020000-000000" / "record.json"
            write_record(old_record, run_status="FAILED", failure_reason="agent_execution_failed")
            write_record(
                new_record,
                run_id="20260706-020000-000000",
                delegation_artifact_revision="2222222222222222222222222222222222222222",
            )

            marked = run_history.mark_superseded_runs(runs, new_record)
            old = json.loads(old_record.read_text(encoding="utf-8"))

        self.assertEqual(marked, ["20260706-010000-000000"])
        self.assertEqual(old["run_status"], "FAILED")
        self.assertEqual(old["failure_reason"], "agent_execution_failed")
        self.assertEqual(old["superseded_reason"], "replacement_delegation_artifact_set")

    def test_unrelated_task_history_is_not_marked(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp)
            old_record = runs / "20260706-010000-000000" / "record.json"
            new_record = runs / "20260706-020000-000000" / "record.json"
            write_record(old_record, delegation_task_file="tasks/other.task.md")
            write_record(
                new_record,
                run_id="20260706-020000-000000",
                delegation_target_base_sha="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                base_sha="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            )

            marked = run_history.mark_superseded_runs(runs, new_record)
            old = json.loads(old_record.read_text(encoding="utf-8"))

        self.assertEqual(marked, [])
        self.assertNotIn("superseded_by_run_id", old)


if __name__ == "__main__":
    unittest.main()
