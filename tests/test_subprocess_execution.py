import subprocess
import unittest
from pathlib import Path
from unittest import mock

from forge import subprocess_execution


class SubprocessExecutionTests(unittest.TestCase):
    def test_run_applies_devnull_stdin_capture_and_timeout(self):
        with mock.patch.object(subprocess_execution.subprocess, "run") as run:
            subprocess_execution.run(
                ["python", "check.py"],
                cwd=Path("worktree"),
                stdin_mode="devnull",
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )

        self.assertEqual(run.call_args.args[0], ["python", "check.py"])
        self.assertEqual(run.call_args.kwargs["cwd"], Path("worktree"))
        self.assertIs(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertTrue(run.call_args.kwargs["text"])
        self.assertTrue(run.call_args.kwargs["capture_output"])
        self.assertEqual(run.call_args.kwargs["timeout"], 30)
        self.assertFalse(run.call_args.kwargs["check"])


    def test_run_leaves_stdin_unspecified_when_inherited(self):
        with mock.patch.object(subprocess_execution.subprocess, "run") as run:
            subprocess_execution.run(["python", "check.py"], stdin_mode="inherit")

        self.assertNotIn("stdin", run.call_args.kwargs)

if __name__ == "__main__":
    unittest.main()
