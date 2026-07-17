import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import target_verify


class Completed:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TargetVerifyTests(unittest.TestCase):
    def test_validate_context_emits_sorted_json_on_success(self):
        output = StringIO()
        with mock.patch.object(
            target_verify,
            "validate_context",
            return_value={"repo_root": "/tmp/target", "base_sha": "abc123"},
        ):
            with redirect_stdout(output):
                result = target_verify.main(
                    [
                        "validate-context",
                        "--record",
                        "record.json",
                        "--config",
                        "gate.toml",
                        "--forge-root",
                        ".",
                    ]
                )

        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue(), '{"base_sha": "abc123", "repo_root": "/tmp/target"}\n')

    def test_verification_check_does_not_inherit_stdin(self):
        with mock.patch.object(target_verify.subprocess, "run", return_value=Completed()) as run:
            check, reason = target_verify.run_check(
                ["python", "check_target.py"],
                cwd=Path("worktree"),
                timeout=30,
            )

        self.assertIsNone(reason)
        self.assertEqual(check["returncode"], 0)
        self.assertIs(run.call_args.kwargs["stdin"], subprocess.DEVNULL)

    def test_acceptance_check_does_not_inherit_stdin_by_default(self):
        artifact = {
            "path": "tasks/example.accept.sh",
            "revision": "a" * 40,
            "sha256": "b" * 64,
            "content": "#!/usr/bin/env bash\nexit 0\n",
        }
        with mock.patch.object(target_verify.subprocess, "run", return_value=Completed()) as run:
            check, reason = target_verify.run_acceptance_check(
                artifact,
                worktree=Path("worktree"),
                timeout=30,
            )

        self.assertIsNone(reason)
        self.assertEqual(check["returncode"], 0)
        self.assertIs(run.call_args.kwargs["stdin"], subprocess.DEVNULL)

    def test_acceptance_check_inherits_normalized_stdin(self):
        artifact = {
            "path": "tasks/example.accept.sh",
            "revision": "a" * 40,
            "sha256": "b" * 64,
            "content": "#!/usr/bin/env bash\nexit 0\n",
        }
        with mock.patch.dict(target_verify.os.environ, {"AXIOM_FORGE_NORMALIZED_STDIN": "1"}):
            with mock.patch.object(target_verify.subprocess, "run", return_value=Completed()) as run:
                check, reason = target_verify.run_acceptance_check(
                    artifact,
                    worktree=Path("worktree"),
                    timeout=30,
                )

        self.assertIsNone(reason)
        self.assertEqual(check["returncode"], 0)
        self.assertNotIn("stdin", run.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()