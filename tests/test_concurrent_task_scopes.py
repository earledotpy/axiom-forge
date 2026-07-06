import tempfile
import unittest
from pathlib import Path

from scripts import concurrent_task_scopes


class ConcurrentTaskScopesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write_task(self, name: str, scope: str | None, acceptance: str | None = "echo ok\n") -> Path:
        task = self.root / f"{name}.task.md"
        task.write_text(f"# {name}\n", encoding="utf-8")
        if scope is not None:
            (self.root / f"{name}.allowed-paths.txt").write_text(scope, encoding="utf-8")
        if acceptance is not None:
            (self.root / f"{name}.accept.sh").write_text(acceptance, encoding="utf-8")
        return task

    def test_overlapping_delegation_ready_scopes_fail_with_stable_reason(self):
        first = self.write_task("first", "app/target.py\ndocs/usage.md\n")
        second = self.write_task("second", "tests/test_target.py\napp/target.py\n")

        with self.assertRaises(concurrent_task_scopes.ConcurrentTaskScopeError) as caught:
            concurrent_task_scopes.check_concurrent_task_scopes([first, second])

        self.assertEqual(caught.exception.reason, "concurrent_task_scope_conflict")
        self.assertEqual(len(caught.exception.conflicts), 1)
        self.assertEqual(caught.exception.conflicts[0].overlapping_paths, ("app/target.py",))

    def test_non_overlapping_delegation_ready_scopes_pass(self):
        first = self.write_task("first", "app/target.py\n")
        second = self.write_task("second", "tests/test_target.py\n")

        ready = concurrent_task_scopes.check_concurrent_task_scopes([first, second])

        self.assertEqual([task.task_file for task in ready], [first.as_posix(), second.as_posix()])

    def test_draft_task_without_approved_scope_is_not_delegation_ready(self):
        draft = self.write_task("draft", None)
        ready = self.write_task("ready", "app/target.py\n")

        checked = concurrent_task_scopes.check_concurrent_task_scopes([draft, ready])

        self.assertEqual(len(checked), 1)
        self.assertEqual(checked[0].task_file, ready.as_posix())

    def test_draft_task_without_acceptance_check_is_not_delegation_ready(self):
        draft = self.write_task("draft", "app/target.py\n", acceptance=None)
        ready = self.write_task("ready", "app/target.py\n")

        concurrent_task_scopes.check_concurrent_task_scopes([draft, ready])

    def test_empty_acceptance_check_is_not_delegation_ready(self):
        draft = self.write_task("draft", "app/target.py\n", acceptance="\n")
        ready = self.write_task("ready", "app/target.py\n")

        concurrent_task_scopes.check_concurrent_task_scopes([draft, ready])


if __name__ == "__main__":
    unittest.main()
