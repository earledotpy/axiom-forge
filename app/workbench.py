from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import webbrowser
from dataclasses import asdict, dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

from scripts.delegation_artifact_set import (
    DelegationArtifactSetError,
    acceptance_check_path,
    load_task_artifact_set,
    scope_sidecar_path,
)
from scripts.target_task_scope import TargetTaskScopeError, validate_scope_path


DEFAULT_ADAPTERS = [
    "codex",
    "claude-code",
    "copilot",
    "opencode",
    "cursor",
    "kiro",
    "qoder",
    "kilo",
    "antigravity",
]


@dataclass(frozen=True)
class IssueReference:
    number: int
    repo: str | None = None


@dataclass(frozen=True)
class IssueContext:
    number: int
    title: str
    body: str
    url: str
    repo: str | None = None


@dataclass(frozen=True)
class DraftTaskPreview:
    authority: str
    source_issue: IssueContext
    task_intent: str
    task_text: str
    target_scope: str
    acceptance_check: str
    draft_adapter: str
    adapter_options: list[str]


@dataclass(frozen=True)
class ApprovedDelegation:
    authority: str
    issue_number: int
    task_file: str
    scope_file: str
    acceptance_file: str
    adapter: str
    delegation_artifact_revision: str


class WorkbenchApprovalError(ValueError):
    pass


IssueFetcher = Callable[[IssueReference], IssueContext]


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
        "number,title,body,url",
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


class WorkbenchServer:
    def __init__(
        self,
        issue_fetcher: IssueFetcher,
        default_repo: str | None = None,
        forge_root: Path | None = None,
    ):
        self.issue_fetcher = issue_fetcher
        self.default_repo = default_repo
        self.forge_root = (forge_root or Path.cwd()).resolve()

    def preview_for_issue(self, raw_reference: str) -> DraftTaskPreview:
        reference = parse_issue_reference(raw_reference, default_repo=self.default_repo)
        issue = self.issue_fetcher(reference)
        return issue_to_draft_preview(issue)

    def approve_draft(self, payload: object) -> ApprovedDelegation:
        approval = _parse_approval(payload)
        task_file = self.forge_root / "tasks" / f"workbench-issue-{approval.issue_number}.task.md"
        scope_file = scope_sidecar_path(task_file)
        acceptance_file = acceptance_check_path(task_file)

        _validate_approval(approval, task_file, acceptance_file)
        _require_clean_forge_repo(self.forge_root)
        if any(path.exists() for path in (task_file, scope_file, acceptance_file)):
            raise WorkbenchApprovalError("delegation_artifact_already_exists")

        task_file.parent.mkdir(parents=True, exist_ok=True)
        task_file.write_text(_approved_task_text(approval.task_text, approval.adapter), encoding="utf-8")
        scope_file.write_text(approval.target_scope, encoding="utf-8")
        acceptance_file.write_text(approval.acceptance_check, encoding="utf-8")

        try:
            artifact_set = load_task_artifact_set(task_file)
        except DelegationArtifactSetError as error:
            raise WorkbenchApprovalError(error.reason) from error

        if artifact_set.state != "delegation-ready":
            raise WorkbenchApprovalError(artifact_set.reason or "invalid_delegation_artifact_set")

        _commit_delegation_artifacts(
            self.forge_root,
            task_file,
            scope_file,
            acceptance_file,
            approval.issue_number,
        )
        revision = _git_output(self.forge_root, ["rev-parse", "HEAD"], "delegation_artifact_revision_unresolved")
        return ApprovedDelegation(
            authority="approved_delegation",
            issue_number=approval.issue_number,
            task_file=task_file.relative_to(self.forge_root).as_posix(),
            scope_file=scope_file.relative_to(self.forge_root).as_posix(),
            acceptance_file=acceptance_file.relative_to(self.forge_root).as_posix(),
            adapter=approval.adapter,
            delegation_artifact_revision=revision,
        )


@dataclass(frozen=True)
class DraftApproval:
    issue_number: int
    task_text: str
    target_scope: str
    acceptance_check: str
    adapter: str


def _parse_approval(payload: object) -> DraftApproval:
    if not isinstance(payload, dict):
        raise WorkbenchApprovalError("invalid_approval_request")
    if payload.get("approved") is not True:
        raise WorkbenchApprovalError("operator_approval_required")

    issue_number = payload.get("issue_number")
    if not isinstance(issue_number, int) or isinstance(issue_number, bool) or issue_number < 1:
        raise WorkbenchApprovalError("invalid_issue_reference")

    fields = ("task_text", "target_scope", "acceptance_check", "adapter")
    if any(not isinstance(payload.get(field), str) for field in fields):
        raise WorkbenchApprovalError("invalid_approval_request")

    return DraftApproval(
        issue_number=issue_number,
        task_text=payload["task_text"],
        target_scope=payload["target_scope"],
        acceptance_check=payload["acceptance_check"],
        adapter=payload["adapter"],
    )


def _validate_approval(approval: DraftApproval, task_file: Path, acceptance_file: Path) -> None:
    if not approval.task_text.strip() or "\x00" in approval.task_text or "\r" in approval.task_text:
        raise WorkbenchApprovalError("invalid_approved_task_text")
    if not approval.acceptance_check.strip() or "\x00" in approval.acceptance_check or "\r" in approval.acceptance_check:
        raise WorkbenchApprovalError("invalid_target_acceptance_check")
    if approval.adapter not in DEFAULT_ADAPTERS:
        raise WorkbenchApprovalError("invalid_approved_adapter")

    approved_paths = _validate_target_scope(approval.target_scope)
    acceptance_repo_path = acceptance_file.relative_to(task_file.parents[1]).as_posix()
    if acceptance_repo_path in approved_paths:
        raise WorkbenchApprovalError("target_acceptance_check_in_scope")


def _validate_target_scope(scope: str) -> frozenset[str]:
    approved_paths = []
    for raw_line in scope.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            approved_paths.append(validate_scope_path(line))
        except TargetTaskScopeError as error:
            raise WorkbenchApprovalError("invalid_target_task_scope") from error
    if not approved_paths:
        raise WorkbenchApprovalError("empty_target_task_scope")
    return frozenset(approved_paths)


def _approved_task_text(task_text: str, adapter: str) -> str:
    return f"<!-- axiom-forge-workbench-approved-adapter: {adapter} -->\n{task_text.rstrip()}\n"


def _require_clean_forge_repo(root: Path) -> None:
    if _git_output(root, ["status", "--porcelain"], "forge_repo_status_failed"):
        raise WorkbenchApprovalError("forge_repo_dirty")


def _commit_delegation_artifacts(
    root: Path,
    task_file: Path,
    scope_file: Path,
    acceptance_file: Path,
    issue_number: int,
) -> None:
    paths = [path.relative_to(root).as_posix() for path in (task_file, scope_file, acceptance_file)]
    _run_git(root, ["add", "--", *paths], "delegation_artifact_stage_failed")
    _run_git(
        root,
        ["commit", "-m", f"Approve workbench delegation for issue #{issue_number}"],
        "delegation_artifact_commit_failed",
    )


def _git_output(root: Path, args: list[str], failure_reason: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise WorkbenchApprovalError(failure_reason)
    return result.stdout.strip()


def _run_git(root: Path, args: list[str], failure_reason: str) -> None:
    _git_output(root, args, failure_reason)


def make_handler(workbench: WorkbenchServer) -> type[BaseHTTPRequestHandler]:
    class WorkbenchRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._write_html(WORKBENCH_HTML)
                return
            if parsed.path == "/api/draft":
                self._handle_draft(parsed.query)
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/approve":
                self._handle_approve()
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def _handle_draft(self, query: str) -> None:
            issue_values = parse_qs(query).get("issue", [])
            if not issue_values:
                self._write_json({"error": "missing_issue_reference"}, HTTPStatus.BAD_REQUEST)
                return
            try:
                preview = workbench.preview_for_issue(issue_values[0])
            except (RuntimeError, ValueError, json.JSONDecodeError) as error:
                self._write_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
                return

            self._write_json(asdict(preview))

        def _handle_approve(self) -> None:
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                if content_length < 1 or content_length > 1_000_000:
                    raise WorkbenchApprovalError("invalid_approval_request")
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                delegation = workbench.approve_draft(payload)
            except (UnicodeDecodeError, ValueError, WorkbenchApprovalError) as error:
                self._write_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
                return

            self._write_json(asdict(delegation), HTTPStatus.CREATED)

        def _write_html(self, body: str) -> None:
            encoded = body.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _write_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
            encoded = json.dumps(payload, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:
            return

    return WorkbenchRequestHandler


def run_server(host: str, port: int, open_browser: bool) -> None:
    workbench = WorkbenchServer(
        issue_fetcher=fetch_issue_with_gh,
        default_repo=default_repo_from_origin(Path.cwd()),
    )
    server = ThreadingHTTPServer((host, port), make_handler(workbench))
    url = f"http://{host}:{server.server_port}/"
    print(f"AXIOM_FORGE_WORKBENCH: {url}", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nAXIOM_FORGE_WORKBENCH: STOP", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start the local Axiom Forge workbench.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="Open the workbench in the default browser.")
    args = parser.parse_args(argv)

    run_server(args.host, args.port, args.open)
    return 0


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


WORKBENCH_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Axiom Forge Workbench</title>
  <style>
    :root {
      color-scheme: light;
      font-family: Arial, sans-serif;
      --ink: #17202a;
      --muted: #637083;
      --line: #d6dde6;
      --panel: #f7f9fb;
      --accent: #0d766e;
      --danger: #b42318;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: #ffffff;
      color: var(--ink);
    }
    header {
      border-bottom: 1px solid var(--line);
      padding: 18px 28px;
    }
    h1 {
      font-size: 22px;
      line-height: 1.2;
      margin: 0;
      letter-spacing: 0;
    }
    main {
      display: grid;
      grid-template-columns: minmax(260px, 360px) minmax(0, 1fr);
      min-height: calc(100vh - 59px);
    }
    aside {
      border-right: 1px solid var(--line);
      padding: 24px 28px;
      background: var(--panel);
    }
    section {
      padding: 24px 32px 40px;
    }
    label {
      display: block;
      font-weight: 700;
      font-size: 13px;
      margin: 18px 0 7px;
    }
    input, textarea, select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      color: var(--ink);
      background: #ffffff;
      font: inherit;
      font-size: 14px;
    }
    input, select {
      min-height: 40px;
      padding: 8px 10px;
    }
    input[type="checkbox"] {
      width: auto;
      min-height: auto;
      margin: 0 8px 0 0;
    }
    textarea {
      min-height: 120px;
      padding: 10px;
      resize: vertical;
      font-family: Consolas, "Liberation Mono", monospace;
      line-height: 1.45;
    }
    button {
      margin-top: 14px;
      width: 100%;
      min-height: 40px;
      border: 0;
      border-radius: 6px;
      background: var(--accent);
      color: #ffffff;
      font-weight: 700;
      cursor: pointer;
    }
    button:disabled {
      cursor: progress;
      opacity: 0.65;
    }
    .meta {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
      overflow-wrap: anywhere;
    }
    .issue {
      border-bottom: 1px solid var(--line);
      padding-bottom: 20px;
      margin-bottom: 22px;
    }
    .issue h2 {
      font-size: 18px;
      margin: 0 0 8px;
      letter-spacing: 0;
    }
    .issue pre {
      white-space: pre-wrap;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 12px;
      max-height: 260px;
      overflow: auto;
      background: #ffffff;
    }
    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 18px;
    }
    .full {
      grid-column: 1 / -1;
    }
    .hidden {
      display: none;
    }
    .error {
      color: var(--danger);
      font-weight: 700;
      margin-top: 12px;
      overflow-wrap: anywhere;
    }
    .approval {
      border-top: 1px solid var(--line);
      margin-top: 24px;
      padding-top: 20px;
    }
    .approval label {
      display: flex;
      align-items: flex-start;
      font-weight: 400;
      line-height: 1.45;
    }
    .approved {
      color: var(--accent);
      font-weight: 700;
      margin-top: 12px;
      overflow-wrap: anywhere;
    }
    @media (max-width: 820px) {
      main, .grid {
        display: block;
      }
      aside {
        border-right: 0;
        border-bottom: 1px solid var(--line);
      }
      section {
        padding: 20px;
      }
    }
  </style>
</head>
<body>
  <header>
    <h1>Axiom Forge Workbench</h1>
  </header>
  <main>
    <aside>
      <form id="issue-form">
        <label for="issue-input">GitHub Issue</label>
        <input id="issue-input" name="issue" placeholder="49 or https://github.com/owner/repo/issues/49" autocomplete="off">
        <button id="load-button" type="submit">Load Draft</button>
        <div id="error" class="error hidden"></div>
      </form>
      <p class="meta">Draft artifacts stay editable here. Only explicit approval creates committed delegation authority.</p>
    </aside>
    <section>
      <div id="empty" class="meta">Load a GitHub Issue to prepare a draft task artifact.</div>
      <div id="preview" class="hidden">
        <div class="issue">
          <h2 id="issue-title"></h2>
          <div id="issue-url" class="meta"></div>
          <pre id="issue-body"></pre>
        </div>
        <div class="grid">
          <div class="full">
            <label for="task-intent">Task Intent</label>
            <textarea id="task-intent"></textarea>
          </div>
          <div class="full">
            <label for="task-text">Task Text</label>
            <textarea id="task-text"></textarea>
          </div>
          <div>
            <label for="target-scope">Target Scope</label>
            <textarea id="target-scope"></textarea>
          </div>
          <div>
            <label for="acceptance-check">Acceptance Check</label>
            <textarea id="acceptance-check"></textarea>
          </div>
          <div>
            <label for="adapter">Draft Adapter</label>
            <select id="adapter"></select>
          </div>
        </div>
        <div class="approval">
          <div class="meta">Draft content is not adapter-facing authority. Approval creates and commits the task, target scope, and acceptance check together.</div>
          <label for="approval-confirmation"><input id="approval-confirmation" type="checkbox">I approve this task text, target scope, acceptance check, and adapter selection as delegation authority.</label>
          <button id="approve-button" type="button">Approve Delegation Artifacts</button>
          <div id="approval-result" class="approved hidden"></div>
        </div>
      </div>
    </section>
  </main>
  <script>
    const form = document.querySelector("#issue-form");
    const button = document.querySelector("#load-button");
    const error = document.querySelector("#error");
    const preview = document.querySelector("#preview");
    const empty = document.querySelector("#empty");
    const approveButton = document.querySelector("#approve-button");
    const approvalConfirmation = document.querySelector("#approval-confirmation");
    const approvalResult = document.querySelector("#approval-result");
    let loadedIssue = null;

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      error.classList.add("hidden");
      button.disabled = true;
      try {
        const issue = encodeURIComponent(document.querySelector("#issue-input").value);
        const response = await fetch(`/api/draft?issue=${issue}`);
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error || "draft_load_failed");
        }
        renderPreview(payload);
      } catch (loadError) {
        error.textContent = loadError.message;
        error.classList.remove("hidden");
      } finally {
        button.disabled = false;
      }
    });

    function renderPreview(payload) {
      const issue = payload.source_issue;
      loadedIssue = issue;
      approvalConfirmation.checked = false;
      approvalResult.classList.add("hidden");
      document.querySelector("#issue-title").textContent = `#${issue.number} ${issue.title}`;
      document.querySelector("#issue-url").textContent = issue.url;
      document.querySelector("#issue-body").textContent = issue.body || "";
      document.querySelector("#task-intent").value = payload.task_intent;
      document.querySelector("#task-text").value = payload.task_text;
      document.querySelector("#target-scope").value = payload.target_scope;
      document.querySelector("#acceptance-check").value = payload.acceptance_check;

      const adapter = document.querySelector("#adapter");
      adapter.replaceChildren(...payload.adapter_options.map((name) => {
        const option = document.createElement("option");
        option.value = name;
        option.textContent = name;
        option.selected = name === payload.draft_adapter;
        return option;
      }));

      empty.classList.add("hidden");
      preview.classList.remove("hidden");
    }

    approveButton.addEventListener("click", async () => {
      error.classList.add("hidden");
      approvalResult.classList.add("hidden");
      if (!loadedIssue) {
        error.textContent = "missing_issue_reference";
        error.classList.remove("hidden");
        return;
      }

      approveButton.disabled = true;
      try {
        const response = await fetch("/api/approve", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            issue_number: loadedIssue.number,
            task_text: document.querySelector("#task-text").value,
            target_scope: document.querySelector("#target-scope").value,
            acceptance_check: document.querySelector("#acceptance-check").value,
            adapter: document.querySelector("#adapter").value,
            approved: approvalConfirmation.checked,
          }),
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error || "delegation_approval_failed");
        }
        approvalResult.textContent = `Approved authority: ${payload.task_file}, ${payload.scope_file}, and ${payload.acceptance_file} at ${payload.delegation_artifact_revision}.`;
        approvalResult.classList.remove("hidden");
      } catch (approvalError) {
        error.textContent = approvalError.message;
        error.classList.remove("hidden");
      } finally {
        approveButton.disabled = false;
      }
    });
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
