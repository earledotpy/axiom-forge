import tempfile
import unittest
from pathlib import Path

from scripts import target_task_scope


class TargetTaskScopeTests(unittest.TestCase):
    def write_sidecar(self, text: str) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "task.scope"
        path.write_text(text, encoding="utf-8")
        return path

    def assert_scope_reason(self, text: str, reason: str):
        path = self.write_sidecar(text)

        with self.assertRaises(target_task_scope.TargetTaskScopeError) as caught:
            target_task_scope.load_scope_sidecar(path)

        self.assertEqual(caught.exception.reason, reason)

    def test_load_scope_accepts_forward_slash_paths_blank_lines_and_comments(self):
        path = self.write_sidecar(
            """
# target task scope
app/target.py

tests/test_target.py
docs/usage.md
"""
        )

        scope = target_task_scope.load_scope_sidecar(path)

        self.assertEqual(
            scope,
            frozenset(["app/target.py", "tests/test_target.py", "docs/usage.md"]),
        )

    def test_missing_sidecar_has_stable_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.scope"

            with self.assertRaises(target_task_scope.TargetTaskScopeError) as caught:
                target_task_scope.load_scope_sidecar(missing)

        self.assertEqual(caught.exception.reason, "target_scope_sidecar_missing")

    def test_empty_effective_scope_has_stable_reason(self):
        self.assert_scope_reason(
            """
# comment only

   # indented comment
""",
            "target_scope_empty",
        )

    def test_absolute_path_has_stable_reason(self):
        self.assert_scope_reason("/app/target.py\n", "target_scope_absolute_path")
        self.assert_scope_reason("C:/target/app.py\n", "target_scope_absolute_path")

    def test_traversal_path_has_stable_reason(self):
        self.assert_scope_reason("../app/target.py\n", "target_scope_traversal")
        self.assert_scope_reason("app/../target.py\n", "target_scope_traversal")

    def test_glob_path_has_stable_reason(self):
        self.assert_scope_reason("app/*.py\n", "target_scope_glob_path")
        self.assert_scope_reason("app/test?.py\n", "target_scope_glob_path")
        self.assert_scope_reason("app/[abc].py\n", "target_scope_glob_path")

    def test_directory_entry_has_stable_reason(self):
        self.assert_scope_reason("app/\n", "target_scope_directory_entry")
        self.assert_scope_reason(".\n", "target_scope_directory_entry")
        self.assert_scope_reason("app/.\n", "target_scope_directory_entry")
        self.assert_scope_reason("app//target.py\n", "target_scope_directory_entry")

    def test_backslash_path_has_stable_reason(self):
        self.assert_scope_reason("app\\target.py\n", "target_scope_backslash_path")

    def test_changed_paths_accept_listed_modify_add_and_delete(self):
        allowed = frozenset(["app/target.py", "docs/usage.md", "new/file.py"])

        target_task_scope.check_changed_paths_allowed(
            allowed,
            [
                target_task_scope.ChangedPath("M", "app/target.py"),
                target_task_scope.ChangedPath("A", "new/file.py"),
                target_task_scope.ChangedPath("D", "docs/usage.md"),
            ],
        )

    def test_changed_paths_reject_unlisted_path(self):
        with self.assertRaises(target_task_scope.TargetTaskScopeError) as caught:
            target_task_scope.check_changed_paths_allowed(
                frozenset(["app/target.py"]),
                [target_task_scope.ChangedPath("M", "docs/usage.md")],
            )

        self.assertEqual(
            caught.exception.reason,
            "target_scope_changed_path_outside_scope",
        )

    def test_rename_requires_old_and_new_path_in_scope(self):
        target_task_scope.check_changed_paths_allowed(
            frozenset(["app/old.py", "app/new.py"]),
            [target_task_scope.ChangedPath("R100", "app/new.py", old_path="app/old.py")],
        )

        with self.assertRaises(target_task_scope.TargetTaskScopeError) as caught:
            target_task_scope.check_changed_paths_allowed(
                frozenset(["app/new.py"]),
                [target_task_scope.ChangedPath("R100", "app/new.py", old_path="app/old.py")],
            )

        self.assertEqual(
            caught.exception.reason,
            "target_scope_changed_path_outside_scope",
        )

    def test_rename_missing_old_path_has_stable_reason(self):
        with self.assertRaises(target_task_scope.TargetTaskScopeError) as caught:
            target_task_scope.check_changed_paths_allowed(
                frozenset(["app/new.py"]),
                [target_task_scope.ChangedPath("R100", "app/new.py")],
            )

        self.assertEqual(caught.exception.reason, "target_scope_rename_missing_old_path")


if __name__ == "__main__":
    unittest.main()
