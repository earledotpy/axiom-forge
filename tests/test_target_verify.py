import subprocess
import sys
import unittest
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

    def test_acceptance_check_inherits_normalized_stdin(self):
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
        self.assertNotIn("stdin", run.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
