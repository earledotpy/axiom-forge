import subprocess
import tempfile
import unittest
from pathlib import Path

from forge.committed_evidence import CommittedEvidenceError, read_committed_file


class CommittedEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(
            ["git", "-C", str(self.root), "config", "user.email", "test@example.invalid"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.root), "config", "user.name", "Axiom Test"],
            check=True,
        )

    def commit_file(self, repo_path: str, content: bytes) -> str:
        path = self.root / repo_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        subprocess.run(["git", "-C", str(self.root), "add", repo_path], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-q", "-m", "add evidence"], check=True)
        return subprocess.check_output(
            ["git", "-C", str(self.root), "rev-parse", "HEAD"], text=True
        ).strip()

    def test_reads_committed_content_with_the_callers_encoding(self):
        revision = self.commit_file("evidence.txt", b"caf\xe9\n")
        (self.root / "evidence.txt").write_text("mutable\n", encoding="utf-8")

        content = read_committed_file(
            self.root,
            revision,
            "evidence.txt",
            missing_reason="missing_evidence",
            encoding="cp1252",
        )

        self.assertEqual(content, "caf\xe9\n")

    def test_missing_committed_content_raises_the_callers_reason(self):
        revision = self.commit_file("present.txt", b"present\n")

        with self.assertRaises(CommittedEvidenceError) as caught:
            read_committed_file(
                self.root,
                revision,
                "missing.txt",
                missing_reason="missing_evidence",
                encoding="utf-8",
            )

        self.assertEqual(caught.exception.reason, "missing_evidence")


if __name__ == "__main__":
    unittest.main()
