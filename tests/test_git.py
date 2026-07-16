import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from forge.git import run_git


class RunGitTests(unittest.TestCase):
    def test_runs_git_in_root_and_preserves_locale_default_decoding(self):
        completed = subprocess.CompletedProcess(["git"], 0, "clean\n", "")
        root = Path("C:/test/repository")

        with patch("forge.git.subprocess.run", return_value=completed) as run:
            result = run_git(root, "status", "--porcelain")

        self.assertIs(result, completed)
        run.assert_called_once_with(
            ["git", "-C", str(root), "status", "--porcelain"],
            text=True,
            capture_output=True,
            check=False,
            encoding=None,
        )


if __name__ == "__main__":
    unittest.main()
