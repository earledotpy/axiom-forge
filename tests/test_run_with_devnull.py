import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_with_devnull


class Completed:
    def __init__(self, returncode):
        self.returncode = returncode


class RunWithDevnullTests(unittest.TestCase):
    def test_runs_command_with_devnull_stdin(self):
        with mock.patch.object(
            run_with_devnull.subprocess,
            "run",
            return_value=Completed(17),
        ) as run:
            result = run_with_devnull.main(["python", "child.py"])

        self.assertEqual(result, 17)
        self.assertEqual(run.call_args.args[0], [sys.executable, "child.py"])
        self.assertIs(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertFalse(run.call_args.kwargs["check"])

    def test_rejects_missing_command(self):
        self.assertEqual(run_with_devnull.main([]), 2)


if __name__ == "__main__":
    unittest.main()