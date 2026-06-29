#!/usr/bin/env python3
"""Evaluate an ordered, contiguous adapter-qualification result series.

Reads all committed results from qualification/results/<adapter>/ in filename
order and refuses to run if that directory has uncommitted changes, so the
series cannot be manipulated by cherry-picking which files are present.
"""

import argparse
import json
import sys

try:
    from qualification_result import check_results_clean, evaluate, load_results_for_adapter
except ImportError:
    from scripts.qualification_result import check_results_clean, evaluate, load_results_for_adapter


parser = argparse.ArgumentParser()
parser.add_argument("--adapter", required=True, help="adapter name")
parser.add_argument("--root", default=".", help="repository root (default: .)")
args = parser.parse_args()

try:
    check_results_clean(args.root, args.adapter)
    results = load_results_for_adapter(args.root, args.adapter)
    outcome = evaluate(results)
except ValueError as exc:
    print(str(exc), file=sys.stderr)
    raise SystemExit(2)

print(json.dumps(outcome, indent=2, sort_keys=True))
