from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from app.workbench_models import DEFAULT_ADAPTERS, DraftTaskPreview, IssueContext, IssueReference

def parse_issue_reference(raw_value: str, default_repo: str | None = None) -> IssueReference:
    value = raw_value.strip()
    if not value:
        raise ValueError("missing_issue_reference")

    parsed = urlparse(value)
    if parsed.netloc.lower() == "github.com":
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 4 and parts[2] == "issues":
            return IssueReference(number=_parse_issue_number(parts[3]), repo=f"{parts[0]}/{parts[1]}")
        raise ValueError("unsupported_github_issue_url")

    if value.startswith("#"):
        value = value[1:]

    return IssueReference(number=_parse_issue_number(value), repo=default_repo)


def issue_to_draft_preview(
    issue: IssueContext, adapter_options: list[str] | None = None
) -> DraftTaskPreview:
    adapters = adapter_options or DEFAULT_ADAPTERS
    task_intent = _task_intent(issue)
    target_scope = _target_scope(issue.body)
    acceptance_check = _acceptance_check(issue)

    task_text = "\n".join(
        [
            f"Implement Issue #{issue.number}: {issue.title}",
            "",
            f"Planning source: {issue.url}",
            "",
            "Task intent:",
            task_intent,
            "",
            "Constraints:",
            "- Keep the patch bounded to the approved target task scope.",
            "- Do not change promotion behavior.",
            "- Do not create run evidence until the operator approves delegation.",
        ]
    )

    return DraftTaskPreview(
        authority="draft_only",
        source_issue=issue,
        task_intent=task_intent,
        task_text=task_text,
        target_scope=target_scope,
        acceptance_check=acceptance_check,
        draft_adapter=adapters[0],
        adapter_options=adapters,
    )


def fetch_issue_with_gh(reference: IssueReference) -> IssueContext:
    command = [
        "gh",
        "issue",
        "view",
        str(reference.number),
        "--json",
        "number,title,body,url,comments",
    ]
    if reference.repo:
        command.extend(["--repo", reference.repo])

    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        reason = result.stderr.strip() or result.stdout.strip() or "gh_issue_view_failed"
        raise RuntimeError(reason)

    issue = json.loads(result.stdout)
    return IssueContext(
        number=int(issue["number"]),
        title=issue["title"],
        body=issue.get("body") or "",
        url=issue["url"],
        repo=reference.repo,
        comments=tuple(
            {
                "author": str((comment.get("author") or {}).get("login") or ""),
                "body": str(comment.get("body") or ""),
                "url": str(comment.get("url") or ""),
            }
            for comment in issue.get("comments", [])
            if isinstance(comment, dict)
        ),
    )


def default_repo_from_origin(root: Path | None = None) -> str | None:
    cwd = root or Path.cwd()
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None

    remote = result.stdout.strip()
    if remote.startswith("git@github.com:"):
        remote = remote.removeprefix("git@github.com:")
        return remote.removesuffix(".git")

    parsed = urlparse(remote)
    if parsed.netloc.lower() == "github.com":
        return parsed.path.strip("/").removesuffix(".git")

    return None



def _parse_issue_number(value: str) -> int:
    if not re.fullmatch(r"\d+", value):
        raise ValueError("invalid_issue_reference")
    number = int(value)
    if number < 1:
        raise ValueError("invalid_issue_reference")
    return number


def _task_intent(issue: IssueContext) -> str:
    preferred_context = _section_first_paragraph(issue.body, "What to build")
    first_paragraph = preferred_context or _first_body_paragraph(issue.body)
    if first_paragraph:
        return f"{issue.title}: {first_paragraph}"
    return issue.title


def _section_first_paragraph(body: str, heading: str) -> str:
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$([\s\S]*?)(?=^##\s+|\Z)",
        re.MULTILINE,
    )
    match = pattern.search(body)
    if not match:
        return ""
    return _first_body_paragraph(match.group(1))


def _first_body_paragraph(body: str) -> str:
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", body)]
    for paragraph in paragraphs:
        normalized = " ".join(line.strip() for line in paragraph.splitlines() if line.strip())
        if normalized and not normalized.startswith("#") and not normalized.startswith("Parent PRD:"):
            return normalized
    return ""


def _target_scope(body: str) -> str:
    paths = sorted(set(re.findall(r"`([A-Za-z0-9_./-]+\.[A-Za-z0-9_./-]+)`", body)))
    if paths:
        return "\n".join(paths)
    return "\n".join(
        [
            "# Draft target paths. Replace these comments before approval.",
            "# Example: app/module.py",
        ]
    )


def _acceptance_check(issue: IssueContext) -> str:
    escaped_title = issue.title.replace('"', '\\"')
    return "\n".join(
        [
            "#!/usr/bin/env bash",
            "set -Eeuo pipefail",
            "",
            f'echo "Draft acceptance for Issue #{issue.number}: {escaped_title}"',
            "# Replace this draft with deterministic target-repository checks before approval.",
        ]
    )
