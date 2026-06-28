#!/usr/bin/env python3
"""Evaluate an ordered, contiguous adapter-qualification result series."""

import argparse
import json
import sys
from qualification_result import evaluate, load_result


parser = argparse.ArgumentParser()
parser.add_argument("results", nargs="+", help="qualification.json files, oldest to newest")
args = parser.parse_args()

try:
    outcome = evaluate([load_result(path) for path in args.results])
except ValueError as exc:
    print(str(exc), file=sys.stderr)
    raise SystemExit(2)

print(json.dumps(outcome, indent=2, sort_keys=True))
