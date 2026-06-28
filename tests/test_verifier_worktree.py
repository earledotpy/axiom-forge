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

        def fake_run(command, cwd=None):
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

    def test_patch_check_failure_stops_before_apply(self):
        calls = []

        def fake_run(command, cwd=None):
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

            def fake_run(command, cwd=None):
                self.assertFalse(created.exists())
                self.assertEqual(command[0:4], ["git", "worktree", "add", "--detach"])
                return Completed()

            with mock.patch.object(verifier_worktree.tempfile, "mkdtemp", fake_mkdtemp):
                with mock.patch.object(verifier_worktree, "run_command", fake_run):
                    worktree = verifier_worktree.create_detached_worktree(
                        Path("repo"), "abc123"
                    )

        self.assertEqual(worktree, created)


if __name__ == "__main__":
    unittest.main()
