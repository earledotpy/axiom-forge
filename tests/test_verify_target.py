import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERIFY_TARGET = ROOT / "scripts" / "verify_target.py"


def _write_config(directory: Path, checks: dict) -> Path:
    required = ", ".join(f'"{name}"' for name in checks)
    lines = [
        "[verify]",
        "timeout_seconds = 60",
        f"required_checks = [{required}]",
        "",
    ]
    for name, command in checks.items():
        rendered = ", ".join(json.dumps(arg) for arg in command)
        lines.append(f"[checks.{name}]")
        lines.append(f"command = [{rendered}]")
        lines.append("")
    config = directory / "gate.toml"
    config.write_text("\n".join(lines), encoding="utf-8")
    return config


def _run_verify(config: Path, worktree: Path, out: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(VERIFY_TARGET),
         "--config", str(config), "--worktree", str(worktree), "--out", str(out)],
        text=True,
        capture_output=True,
        timeout=60,
    )


class VerifyTargetOutputTests(unittest.TestCase):
    """Guards issue #104: verify runs checks with file-backed stdio (not captured
    pipes), while still recording each check's stdout/stderr and returncode."""

    def test_output_captured_and_pass_fail_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            config = _write_config(
                tmp,
                {
                    "ok": [sys.executable, "-c",
                           "import sys; print('out-ok'); "
                           "print('err-ok', file=sys.stderr)"],
                    "bad": [sys.executable, "-c",
                            "import sys; print('out-bad'); sys.exit(3)"],
                },
            )
            out = tmp / "result.json"
            completed = _run_verify(config, ROOT, out)

            self.assertEqual(completed.returncode, 1)  # overall FAIL (bad failed)
            result = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "FAIL")

            ok = result["checks"]["ok"]
            self.assertEqual(ok["status"], "PASS")
            self.assertEqual(ok["returncode"], 0)
            self.assertIn("out-ok", ok["stdout"])
            self.assertIn("err-ok", ok["stderr"])

            bad = result["checks"]["bad"]
            self.assertEqual(bad["status"], "FAIL")
            self.assertEqual(bad["returncode"], 3)
            self.assertIn("out-bad", bad["stdout"])

    def test_check_stdin_is_detached(self):
        # A child that reads stdin must see EOF immediately, never block: verify
        # runs checks with stdin detached (devnull), so suite subprocesses cannot
        # inherit a live stdin handle.
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            config = _write_config(
                tmp,
                {"reads_stdin": [sys.executable, "-c",
                                 "import sys; data = sys.stdin.read(); "
                                 "print('stdin=%r' % data)"]},
            )
            out = tmp / "result.json"
            completed = _run_verify(config, ROOT, out)

            self.assertEqual(completed.returncode, 0)
            result = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(result["checks"]["reads_stdin"]["returncode"], 0)
            self.assertIn("stdin=''", result["checks"]["reads_stdin"]["stdout"])


if __name__ == "__main__":
    unittest.main()
