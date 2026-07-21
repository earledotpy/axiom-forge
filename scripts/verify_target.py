#!/usr/bin/env python3
import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forge import subprocess_execution
from forge.small_helpers import utc_now as shared_utc_now

try:
    import tomllib
except ModuleNotFoundError:
    print("Python 3.11+ required: missing tomllib", file=sys.stderr)
    sys.exit(2)


def utc_now() -> str:
    return shared_utc_now()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--worktree", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    config_path = Path(args.config)
    worktree = Path(args.worktree)

    result = {
        "schema_version": 1,
        "status": "FAIL",
        "timestamp_utc": utc_now(),
        "worktree": str(worktree),
        "checks": {}
    }

    try:
        cfg = tomllib.loads(config_path.read_text(encoding="utf-8"))
        timeout = int(cfg["verify"].get("timeout_seconds", 300))
        required = cfg["verify"]["required_checks"]
        checks = cfg["checks"]
    except Exception as exc:
        result["reason"] = f"malformed_gate_config: {exc}"
        Path(args.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(result["reason"], file=sys.stderr)
        return 1

    all_pass = True

    for name in required:
        check_result = {
            "status": "FAIL",
            "command": None,
            "returncode": None,
            "stdout": "",
            "stderr": ""
        }

        try:
            command = checks[name]["command"]
            check_result["command"] = command

            # Redirect the gate check's stdout/stderr to files rather than
            # capturing into OS pipes. Tests inside the suite spawn their own
            # subprocesses that inherit the parent's stdio handles; on Windows,
            # inherited pipe handles intermittently trip handle races (issue
            # #104), surfacing as a spurious verification_failed. File-backed
            # stdio plus a detached stdin hand children no pipe handles to race
            # on. The gate (uncaptured `unittest discover`) is deterministically
            # green, so the flake is a verify-runner artifact, not a real fail.
            with tempfile.TemporaryDirectory(prefix="verify_target_") as logdir:
                out_path = Path(logdir) / "stdout.log"
                err_path = Path(logdir) / "stderr.log"
                with open(out_path, "wb") as out_fh, open(err_path, "wb") as err_fh:
                    completed = subprocess_execution.run(
                        command,
                        cwd=worktree,
                        stdin_mode="devnull",
                        timeout=timeout,
                        stdout=out_fh,
                        stderr=err_fh,
                    )
                check_result["returncode"] = completed.returncode
                check_result["stdout"] = out_path.read_text(
                    encoding="utf-8", errors="replace"
                )
                check_result["stderr"] = err_path.read_text(
                    encoding="utf-8", errors="replace"
                )

            if completed.returncode == 0:
                check_result["status"] = "PASS"
            else:
                all_pass = False

        except Exception as exc:
            all_pass = False
            check_result["status"] = "ERROR"
            check_result["stderr"] = str(exc)

        result["checks"][name] = check_result

    result["status"] = "PASS" if all_pass else "FAIL"
    Path(args.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print(f"VERIFY_TARGET: {result['status']}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
