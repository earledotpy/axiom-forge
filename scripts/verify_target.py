#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    print("Python 3.11+ required: missing tomllib", file=sys.stderr)
    sys.exit(2)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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

            completed = subprocess.run(
                command,
                cwd=worktree,
                text=True,
                capture_output=True,
                timeout=timeout
            )

            check_result["returncode"] = completed.returncode
            check_result["stdout"] = completed.stdout
            check_result["stderr"] = completed.stderr

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
