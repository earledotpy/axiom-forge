#!/usr/bin/env python3
"""Render reviewable Markdown evidence snippets from qualification result files.

Emits a snippet to stdout; never modifies committed docs.
"""

import argparse
import json
import sys

try:
    from qualification_result import (
        check_results_clean,
        classify_series,
        evaluate,
        load_results_for_adapter,
    )
except ImportError:
    from scripts.qualification_result import (
        check_results_clean,
        classify_series,
        evaluate,
        load_results_for_adapter,
    )


def render_qualification_snippet(outcome):
    """Return a Markdown snippet string from a QUALIFIED outcome dict.

    Raises ValueError if the outcome is not QUALIFIED.
    """
    if outcome.get("status") != "QUALIFIED":
        reason = outcome.get("reason") or "unknown"
        raise ValueError(f"not_qualified:{reason}")

    adapter = outcome.get("adapter") or ""
    config = outcome.get("pinned_configuration") or {}
    qualifying_results = outcome.get("qualifying_results") or []

    lines = []

    lines.append(f"## {adapter} Qualification")
    lines.append("")
    lines.append("Status: QUALIFIED")
    lines.append("")
    lines.append(f"- Adapter: {adapter}")
    lines.append(
        f"- Adapter script: `{config.get('adapter_script', '')}` "
        f"revision `{config.get('adapter_script_revision', '')}`"
    )
    lines.append(f"- CLI command: `{config.get('cli_command', '')}`")
    lines.append(f"- CLI path: `{config.get('cli_path', '')}`")
    lines.append(f"- CLI version: `{config.get('cli_version', '')}`")
    lines.append(f"- Selected model: `{config.get('selected_model', '')}`")
    rel_conf = config.get("relevant_configuration") or {}
    lines.append(f"- Relevant configuration: `{json.dumps(rel_conf)}`")
    lines.append("")

    header = (
        "| Case | Run ID | Task specification | "
        "Allowed-path specification | Acceptance specification | "
        "Patch SHA-256 | Scope | Acceptance |"
    )
    separator = "| --- | --- | --- | --- | --- | --- | --- | --- |"
    lines.append(header)
    lines.append(separator)

    for result in qualifying_results:
        case = result.get("case", "")
        run_id = result.get("run_id", "")
        patch_sha = result.get("patch_sha256", "")
        scope = result.get("scope", "")
        acceptance = result.get("acceptance", "")
        case_spec = result.get("case_spec") or {}

        task_cell = _spec_cell(case_spec.get("task") or {})
        allowed_cell = _spec_cell(case_spec.get("allowed_paths") or {})
        accept_cell = _spec_cell(case_spec.get("acceptance") or {})

        lines.append(
            f"| {case} | `{run_id}` | {task_cell} | "
            f"{allowed_cell} | {accept_cell} | `{patch_sha}` | {scope} | {acceptance} |"
        )

    return "\n".join(lines) + "\n"


def _spec_cell(spec):
    path = spec.get("path", "")
    sha = spec.get("sha256", "")
    return f"`{path}` `{sha}`"


def render_evidence_reuse_snippet(classification):
    """Return a Markdown snippet interpreting an adapter's committed
    qualification results as historical evidence under the
    compatibility/trust split.

    Unlike render_qualification_snippet(), this covers every committed
    result for the adapter, not only a QUALIFIED series, and cites each
    result's source file so an operator can trace the interpretation back to
    the evidence that produced it.
    """
    adapter = classification.get("adapter") or ""
    status = classification.get("standard_trust_status")
    reason = classification.get("standard_trust_reason")
    items = classification.get("items") or []

    lines = []
    lines.append(f"## {adapter} Historical Evidence Reuse")
    lines.append("")
    trust_line = f"Standard trust status: {status}"
    if reason:
        trust_line += f" ({reason})"
    lines.append(trust_line)
    lines.append("")

    header = (
        "| Source | Run ID | Case | Compatibility evidence | "
        "Standard trust contribution | Identity |"
    )
    separator = "| --- | --- | --- | --- | --- | --- |"
    lines.append(header)
    lines.append(separator)

    for item in items:
        compatibility = "YES" if item.get("compatibility_evidence") else "NO"
        contribution = "YES" if item.get("standard_trust_contribution") else "NO"
        lines.append(
            f"| `{item.get('source', '')}` | `{item.get('run_id', '')}` | "
            f"{item.get('case', '')} | {compatibility} | {contribution} | "
            f"{item.get('identity_status', '')} |"
        )

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="Render a reviewable Markdown snippet from qualification result files."
    )
    parser.add_argument("--adapter", required=True, help="adapter name")
    parser.add_argument("--root", default=".", help="repository root (default: .)")
    parser.add_argument(
        "--evidence-reuse",
        action="store_true",
        help=(
            "render a historical evidence reuse report covering every "
            "committed result, instead of the QUALIFIED-only snippet"
        ),
    )
    args = parser.parse_args()

    try:
        check_results_clean(args.root, args.adapter)
        if args.evidence_reuse:
            classification = classify_series(args.root, args.adapter)
            snippet = render_evidence_reuse_snippet(classification)
        else:
            loaded = load_results_for_adapter(args.root, args.adapter)
            outcome = evaluate(loaded)
            snippet = render_qualification_snippet(outcome)
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(snippet, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
