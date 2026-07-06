#!/usr/bin/env python
import argparse
from pathlib import Path
import sys

from concurrent_task_scopes import ConcurrentTaskScopeError, check_concurrent_task_scopes


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check active delegation-ready tasks for overlapping approved scopes."
    )
    parser.add_argument("task_files", nargs="+", help="Task files to consider for parallel delegation.")
    args = parser.parse_args()

    try:
        ready_tasks = check_concurrent_task_scopes([Path(task) for task in args.task_files])
    except ConcurrentTaskScopeError as exc:
        print("CONCURRENT_TASK_SCOPE_CHECK: FAIL", file=sys.stderr)
        print(f"Reason: {exc.reason}", file=sys.stderr)
        for conflict in exc.conflicts:
            print(
                "Conflict: "
                f"{conflict.first_task_file} "
                f"{conflict.second_task_file} "
                f"paths={','.join(conflict.overlapping_paths)}",
                file=sys.stderr,
            )
        return 1

    print("CONCURRENT_TASK_SCOPE_CHECK: PASS")
    print(f"Delegation-ready tasks checked: {len(ready_tasks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
