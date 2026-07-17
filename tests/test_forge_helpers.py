import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from forge import small_helpers


class ForgeSmallHelperTests(unittest.TestCase):
    def test_utc_now_uses_the_existing_zulu_second_precision_format(self):
        self.assertRegex(
            small_helpers.utc_now(),
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
        )

    def test_optional_json_read_keeps_missing_and_valid_file_behavior(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            valid = root / "valid.json"
            valid.write_text(json.dumps({"answer": 42}), encoding="utf-8")

            self.assertIsNone(small_helpers.read_optional_json(root / "missing.json"))
            self.assertEqual(small_helpers.read_optional_json(valid), {"answer": 42})

    def test_sha256_file_produces_the_existing_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "payload.txt"
            path.write_bytes(b"Axiom Forge\n")

            self.assertEqual(
                small_helpers.sha256_file(path),
                hashlib.sha256(b"Axiom Forge\n").hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()
