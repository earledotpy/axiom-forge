import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import verifier_worktree


class Completed:
    def __init__(self, returncode=0):
        self.returncode = returncode


class VerifierWorktreeTests(unittest.TestCase):
    def test_apply_patch_checks_before_applying(self):
        calls = []

        def fake_run(command, cwd=None, stdout=None, stderr=None):
            calls.append((command, cwd))
            return Completed()

        with mock.patch.object(verifier_worktree, "run_command", fake_run):
            verifier_worktree.apply_patch(Path("worktree"), Path("patch.diff"))

        self.assertEqual(
            calls,
            [
                (
                    [
                        "git",
                        "-C",
                        "worktree",
                        "apply",
                        "--check",
                        "--whitespace=error",
                        "patch.diff",
                    ],
                    None,
                ),
                (
                    [
                        "git",
                        "-C",
                        "worktree",
                        "apply",
                        "--whitespace=error",
                        "patch.diff",
                    ],
                    None,
                ),
            ],
        )

    def test_changed_paths_after_apply_routes_through_subprocess_execution(self):
        completed = mock.Mock(returncode=0, stdout="M\tapp/x.py\n")

        with mock.patch.object(verifier_worktree.subprocess_execution, "run", return_value=completed) as run:
            changed = verifier_worktree.changed_paths_after_apply(Path("worktree"))

        self.assertEqual(
            run.call_args.args[0],
            ["git", "-C", "worktree", "diff", "--name-status", "-M", "--no-ext-diff"],
        )
        self.assertTrue(run.call_args.kwargs["text"])
        self.assertTrue(run.call_args.kwargs["capture_output"])
        self.assertFalse(run.call_args.kwargs["check"])
        self.assertEqual([(path.status, path.path) for path in changed], [("M", "app/x.py")])

    def test_patch_check_failure_stops_before_apply(self):
        calls = []

        def fake_run(command, cwd=None, stdout=None, stderr=None):
            calls.append(command)
            return Completed(1)

        with mock.patch.object(verifier_worktree, "run_command", fake_run):
            with self.assertRaises(verifier_worktree.VerifierError) as caught:
                verifier_worktree.apply_patch(Path("worktree"), Path("patch.diff"))

        self.assertEqual(caught.exception.returncode, verifier_worktree.PATCH_CHECK_FAILED)
        self.assertEqual(len(calls), 1)

    def test_verify_detached_cleans_up_worktree_after_verification_failure(self):
        events = []

        def fake_create(repo_root, base_sha):
            events.append(("create", repo_root, base_sha))
            return Path("verify-worktree")

        def fake_apply(worktree, patch):
            events.append(("apply", worktree, patch))

        def fake_verify(script_dir, config, worktree, out):
            events.append(("verify", script_dir, config, worktree, out))
            raise verifier_worktree.VerifierError(verifier_worktree.VERIFICATION_FAILED)

        def fake_remove(repo_root, worktree):
            events.append(("remove", repo_root, worktree))

        with mock.patch.object(verifier_worktree, "create_detached_worktree", fake_create):
            with mock.patch.object(verifier_worktree, "apply_patch", fake_apply):
                with mock.patch.object(verifier_worktree, "verify_target", fake_verify):
                    with mock.patch.object(verifier_worktree, "remove_worktree", fake_remove):
                        with self.assertRaises(verifier_worktree.VerifierError):
                            verifier_worktree.verify_detached(
                                Path("repo"),
                                Path("scripts"),
                                "abc123",
                                Path("patch.diff"),
                                Path("gate.toml"),
                                Path("verify.json"),
                            )

        self.assertEqual(events[-1], ("remove", Path("repo"), Path("verify-worktree")))

    def test_create_detached_worktree_removes_temp_directory_before_git_add(self):
        with tempfile.TemporaryDirectory() as tmp:
            created = Path(tmp) / "created"

            def fake_mkdtemp():
                created.mkdir()
                return str(created)

            def fake_run(command, cwd=None, stdout=None, stderr=None):
                self.assertFalse(created.exists())
                self.assertEqual(command[0:4], ["git", "worktree", "add", "--detach"])
                return Completed()

            with mock.patch.object(verifier_worktree.tempfile, "mkdtemp", fake_mkdtemp):
                with mock.patch.object(verifier_worktree, "run_command", fake_run):
                    worktree = verifier_worktree.create_detached_worktree(
                        Path("repo"), "abc123"
                    )

        self.assertEqual(worktree, created)

    def test_create_detached_cli_prints_created_worktree(self):
        with mock.patch.object(verifier_worktree, "create_detached_worktree") as fake_create:
            fake_create.return_value = Path("verify-worktree")

            with mock.patch("builtins.print") as fake_print:
                status = verifier_worktree.main(
                    [
                        "create-detached",
                        "--repo-root",
                        "repo",
                        "--base-sha",
                        "abc123",
                    ]
                )

        self.assertEqual(status, 0)
        fake_create.assert_called_once_with(Path("repo"), "abc123")
        fake_print.assert_called_once_with(Path("verify-worktree"))


if __name__ == "__main__":
    unittest.main()
