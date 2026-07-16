import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMMAND = [sys.executable, str(ROOT / "scripts" / "json_shell_vars.py")]


class JsonShellVarsCommandTests(unittest.TestCase):
    def write_payload(self, content: str) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "payload.json"
        path.write_text(content, encoding="utf-8")
        return path

    def test_extract_emits_eval_safe_assignments_for_verbatim_values(self):
        payload = self.write_payload(
            json.dumps(
                {
                    "phrase": "two words",
                    "shell": "$(not-a-command) 'quoted'",
                    "empty": "",
                    "missing_value": None,
                }
            )
        )

        result = subprocess.run(
            [*COMMAND, "extract", "--file", str(payload), "phrase", "shell", "empty", "missing_value"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        assignments = self.write_payload(result.stdout)
        evaluated = subprocess.check_output(
            [
                "bash",
                "-c",
                "set -eu; eval \"$(cat \"$1\")\"; "
                "printf '%s\\0%s\\0%s\\0%s' \"$phrase\" \"$shell\" \"$empty\" \"$missing_value\"",
                "bash",
                str(assignments),
            ]
        )
        self.assertEqual(
            evaluated.split(b"\0"),
            [b"two words", b"$(not-a-command) 'quoted'", b"", b""],
        )

    def test_extract_fails_closed_for_malformed_payload_or_missing_key(self):
        malformed = self.write_payload("not json")
        missing_key = self.write_payload('{"present": "value"}')

        malformed_result = subprocess.run(
            [*COMMAND, "extract", "--file", str(malformed), "present"],
            text=True,
            capture_output=True,
            check=False,
        )
        missing_key_result = subprocess.run(
            [*COMMAND, "extract", "--file", str(missing_key), "missing"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual((malformed_result.returncode, malformed_result.stdout), (1, "invalid_json_payload\n"))
        self.assertEqual(
            (missing_key_result.returncode, missing_key_result.stdout),
            (1, "missing_json_key_missing\n"),
        )

    def test_build_writes_one_json_payload_without_shell_concatenation(self):
        result = subprocess.run(
            [
                *COMMAND,
                "build",
                "--field",
                "message",
                "two words and a 'quote'",
                "--field",
                "empty",
                "",
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            json.loads(result.stdout),
            {"message": "two words and a 'quote'", "empty": ""},
        )


if __name__ == "__main__":
    unittest.main()
