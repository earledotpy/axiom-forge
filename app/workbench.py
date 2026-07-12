from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import webbrowser
from threading import Lock
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
    validate_delegation_task_file,
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


class WorkbenchExecutionError(ValueError):
    pass


class WorkbenchVerificationError(ValueError):
    pass


@dataclass(frozen=True)
class OperatorEvidenceSummary:
    authority: str
    run_id: str
    task_intent: str
    approved_scope: list[str]
    adapter: str
    run_status: str
    changed_paths: list[str]
    verification_result: str
    verification_reason: str | None
    acceptance_result: str
    failure_reason: str | None
    next_allowed_actions: list[str]


@dataclass(frozen=True)
class OperatorEvidenceDetails:
    run_id: str
    stdout: str
    stderr: str
    patch_diff: str

@dataclass(frozen=True)
class CapturedRun:
    authority: str
    run_id: str
    run_status: str
    failure_reason: str | None


@dataclass(frozen=True)
class ConfirmedExecution:
    task_file: str


@dataclass(frozen=True)
class ConfirmedRetry:
    run_id: str
    adapter: str


VerificationRunner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]
IssueFetcher = Callable[[IssueReference], IssueContext]
TargetRunner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]


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
        target_runner: TargetRunner | None = None,
        verification_runner: VerificationRunner | None = None,
    ):
        self.issue_fetcher = issue_fetcher
        self.default_repo = default_repo
        self.forge_root = (forge_root or Path.cwd()).resolve()
        self._target_runner = target_runner or _run_target_mode_runner
        self._verification_runner = verification_runner or _run_target_mode_verifier
        self._active_delegation_lock = Lock()
        self._active_delegation = False

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

    def execute_confirmed_delegation(self, payload: object) -> CapturedRun:
        execution = _parse_confirmed_execution(payload)
        _, adapter = _approved_execution_target(self.forge_root, execution.task_file)
        return self._run_confirmed_delegation(execution.task_file, adapter)

    def retry_confirmed_delegation(self, payload: object) -> CapturedRun:
        retry = _parse_confirmed_retry(payload)
        task_file = _retry_execution_target(self.forge_root, retry.run_id)
        return self._run_confirmed_delegation(task_file, retry.adapter)

    def _run_confirmed_delegation(self, task_file: str, adapter: str) -> CapturedRun:
        command = [
            "bash",
            str(self.forge_root / "scripts" / "run_agent_task.sh"),
            "--target",
            adapter,
            task_file,
        ]
        with self._active_delegation_lock:
            if self._active_delegation:
                raise WorkbenchExecutionError("active_workbench_delegation_in_progress")
            self._active_delegation = True
        try:
            result = self._target_runner(command, self.forge_root)
        except OSError as error:
            raise WorkbenchExecutionError("target_mode_runner_start_failed") from error
        finally:
            with self._active_delegation_lock:
                self._active_delegation = False

        return _captured_run_from_runner_result(self.forge_root, result)


    def verify_captured_run(self, payload: object) -> OperatorEvidenceSummary:
        run_id = _parse_verification_request(payload)
        run_dir = _captured_run_directory(self.forge_root, run_id)
        command = [
            "bash",
            str(self.forge_root / "scripts" / "verify_patch.sh"),
            "--target",
            run_dir.relative_to(self.forge_root).as_posix(),
        ]
        try:
            result = self._verification_runner(command, self.forge_root)
        except OSError as error:
            raise WorkbenchVerificationError("target_mode_verifier_start_failed") from error
        return _operator_evidence_summary(
            run_dir,
            verification_failure_reason=_verification_failure_reason(result),
        )

    def summary_for_captured_run(self, run_id: str) -> OperatorEvidenceSummary:
        return _operator_evidence_summary(_captured_run_directory(self.forge_root, run_id))

    def evidence_details_for_captured_run(self, run_id: str) -> OperatorEvidenceDetails:
        run_dir = _captured_run_directory(self.forge_root, run_id)
        return OperatorEvidenceDetails(
            run_id=run_id,
            stdout=_evidence_text(run_dir / "stdout.log"),
            stderr=_evidence_text(run_dir / "stderr.log"),
            patch_diff=_evidence_text(run_dir / "patch.diff"),
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


def _parse_confirmed_execution(payload: object) -> ConfirmedExecution:
    if not isinstance(payload, dict):
        raise WorkbenchExecutionError("invalid_execution_request")
    if "command" in payload:
        raise WorkbenchExecutionError("generic_command_execution_forbidden")
    if set(payload) != {"task_file", "confirmed"}:
        raise WorkbenchExecutionError("invalid_execution_request")
    if payload.get("confirmed") is not True:
        raise WorkbenchExecutionError("operator_execution_confirmation_required")
    task_file = payload.get("task_file")
    if not isinstance(task_file, str):
        raise WorkbenchExecutionError("invalid_execution_request")
    return ConfirmedExecution(task_file=task_file)


def _parse_confirmed_retry(payload: object) -> ConfirmedRetry:
    if not isinstance(payload, dict) or set(payload) != {"run_id", "adapter", "confirmed"}:
        raise WorkbenchExecutionError("invalid_retry_request")
    if payload.get("confirmed") is not True:
        raise WorkbenchExecutionError("operator_retry_confirmation_required")
    run_id = payload.get("run_id")
    adapter = payload.get("adapter")
    if not isinstance(run_id, str) or not _is_captured_run_id(run_id):
        raise WorkbenchExecutionError("invalid_captured_run_reference")
    if not isinstance(adapter, str) or adapter not in DEFAULT_ADAPTERS:
        raise WorkbenchExecutionError("invalid_retry_adapter")
    return ConfirmedRetry(run_id=run_id, adapter=adapter)


def _approved_execution_target(root: Path, task_file_value: str) -> tuple[Path, str]:
    try:
        task_path = validate_delegation_task_file(task_file_value)
        task_file = (root / task_path).resolve()
        task_file.relative_to(root)
        artifact_set = load_task_artifact_set(task_file)
    except (DelegationArtifactSetError, ValueError) as error:
        raise WorkbenchExecutionError("invalid_approved_delegation") from error

    if artifact_set.state != "delegation-ready" or not artifact_set.approved_adapter:
        raise WorkbenchExecutionError("invalid_approved_delegation")
    return task_file, artifact_set.approved_adapter


def _retry_execution_target(root: Path, run_id: str) -> str:
    try:
        run_dir = _captured_run_directory(root, run_id)
        summary = _operator_evidence_summary(run_dir)
    except WorkbenchVerificationError as error:
        raise WorkbenchExecutionError(str(error)) from error
    if summary.run_status != "FAILED" and summary.verification_result != "FAIL":
        raise WorkbenchExecutionError("captured_run_not_retryable")

    record = _evidence_json(run_dir / "record.json")
    task_file = record.get("delegation_task_file")
    revision = record.get("delegation_artifact_revision")
    if not isinstance(task_file, str) or not isinstance(revision, str) or not revision:
        raise WorkbenchExecutionError("retry_delegation_provenance_unavailable")
    task_path, _ = _approved_execution_target(root, task_file)
    _require_retry_delegation_boundary(root, revision, task_path)
    return task_file


def _require_retry_delegation_boundary(root: Path, revision: str, task_file: Path) -> None:
    for artifact in (task_file, scope_sidecar_path(task_file), acceptance_check_path(task_file)):
        try:
            repo_path = artifact.relative_to(root).as_posix()
            current_content = artifact.read_text(encoding="utf-8")
        except (OSError, ValueError) as error:
            raise WorkbenchExecutionError("retry_delegation_provenance_unavailable") from error
        expected_content = _retry_revision_artifact_content(root, revision, repo_path)
        if current_content != expected_content:
            raise WorkbenchExecutionError("retry_delegation_boundary_changed")


def _retry_revision_artifact_content(root: Path, revision: str, repo_path: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "show", f"{revision}:{repo_path}"],
        text=True,
        capture_output=True,
        check=False,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise WorkbenchExecutionError("retry_delegation_provenance_unavailable")
    return result.stdout

def _run_target_mode_runner(command: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=root, text=True, capture_output=True, check=False)


def _captured_run_from_runner_result(
    root: Path, result: subprocess.CompletedProcess[str]
) -> CapturedRun:
    output = f"{result.stdout}\n{result.stderr}"
    match = re.search(r"^RUN_(?:CAPTURED|FAILED): ([0-9]{8}-[0-9]{6}-[0-9]+)$", output, re.MULTILINE)
    if not match:
        raise WorkbenchExecutionError("target_mode_runner_did_not_capture_run")

    run_id = match.group(1)
    record_path = root / "runs" / run_id / "record.json"
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WorkbenchExecutionError("captured_run_record_unavailable") from error
    if record.get("run_id") != run_id or record.get("run_status") not in {"COMPLETED", "FAILED"}:
        raise WorkbenchExecutionError("captured_run_record_invalid")
    failure_reason = record.get("failure_reason")
    if failure_reason is not None and not isinstance(failure_reason, str):
        raise WorkbenchExecutionError("captured_run_record_invalid")

    return CapturedRun(
        authority="captured_run",
        run_id=run_id,
        run_status=record["run_status"],
        failure_reason=failure_reason,
    )

def _parse_verification_request(payload: object) -> str:
    if not isinstance(payload, dict) or set(payload) != {"run_id"}:
        raise WorkbenchVerificationError("invalid_verification_request")
    run_id = payload.get("run_id")
    if not isinstance(run_id, str) or not _is_captured_run_id(run_id):
        raise WorkbenchVerificationError("invalid_captured_run_reference")
    return run_id


def _is_captured_run_id(run_id: str) -> bool:
    return re.fullmatch(r"[0-9]{8}-[0-9]{6}-[0-9]+", run_id) is not None


def _captured_run_directory(root: Path, run_id: str) -> Path:
    if not _is_captured_run_id(run_id):
        raise WorkbenchVerificationError("invalid_captured_run_reference")
    run_dir = root / "runs" / run_id
    try:
        run_dir.resolve().relative_to((root / "runs").resolve())
    except ValueError as error:
        raise WorkbenchVerificationError("invalid_captured_run_reference") from error
    if not run_dir.is_dir():
        raise WorkbenchVerificationError("captured_run_not_found")
    return run_dir


def _run_target_mode_verifier(command: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=root, text=True, capture_output=True, check=False)


def _operator_evidence_summary(
    run_dir: Path, verification_failure_reason: str | None = None
) -> OperatorEvidenceSummary:
    try:
        record = json.loads((run_dir / "record.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WorkbenchVerificationError("captured_run_record_unavailable") from error
    if not isinstance(record, dict) or record.get("run_id") != run_dir.name:
        raise WorkbenchVerificationError("captured_run_record_invalid")

    run_status = record.get("run_status")
    if not isinstance(run_status, str):
        run_status = "missing_run_status"
    failure_reason = record.get("failure_reason")
    if not isinstance(failure_reason, str):
        failure_reason = None
    verification_result, verification_reason, acceptance_result = _verification_summary(
        run_dir, verification_failure_reason
    )
    return OperatorEvidenceSummary(
        authority="operator_evidence_summary",
        run_id=run_dir.name,
        task_intent=_task_intent_from_evidence(run_dir),
        approved_scope=_scope_from_evidence(run_dir),
        adapter=record.get("agent") if isinstance(record.get("agent"), str) else "missing_adapter",
        run_status=run_status,
        changed_paths=_changed_paths_from_evidence(run_dir),
        verification_result=verification_result,
        verification_reason=verification_reason,
        acceptance_result=acceptance_result,
        failure_reason=failure_reason,
        next_allowed_actions=_next_allowed_actions(run_status, verification_result),
    )


def _evidence_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}

def _verification_summary(
    run_dir: Path, verification_failure_reason: str | None
) -> tuple[str, str | None, str]:
    verify_path = run_dir / "verify.json"
    if not verify_path.is_file():
        if verification_failure_reason is None:
            return "NOT_RUN", None, "NOT_RUN"
        return "FAIL", verification_failure_reason, "NOT_RUN"
    try:
        verify = json.loads(verify_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "FAIL", "invalid_verification_evidence", "NOT_RUN"
    if not isinstance(verify, dict):
        return "FAIL", "invalid_verification_evidence", "NOT_RUN"
    status = "PASS" if verify.get("status") == "PASS" else "FAIL"
    reason = verify.get("reason") if isinstance(verify.get("reason"), str) else verification_failure_reason
    acceptance = verify.get("acceptance")
    if not isinstance(acceptance, dict) or not isinstance(acceptance.get("returncode"), int):
        acceptance_result = "NOT_RUN"
    else:
        acceptance_result = "PASS" if acceptance["returncode"] == 0 else "FAIL"
    return status, reason, acceptance_result


def _task_intent_from_evidence(run_dir: Path) -> str:
    task_lines = _evidence_text(run_dir / "task.md").splitlines()
    for index, line in enumerate(task_lines):
        if line.strip() == "Task intent:":
            intent_lines = []
            for intent_line in task_lines[index + 1:]:
                if intent_line.strip() == "Constraints:":
                    break
                intent_lines.append(intent_line)
            task_intent = "\n".join(intent_lines).strip()
            if task_intent:
                return task_intent
    for line in task_lines:
        if line.strip() and not line.lstrip().startswith("<!--"):
            return line.strip()
    return "missing_task_intent"

def _scope_from_evidence(run_dir: Path) -> list[str]:
    return [
        line.strip()
        for line in _evidence_text(run_dir / "allowed-paths.txt").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _changed_paths_from_evidence(run_dir: Path) -> list[str]:
    paths: list[str] = []
    for line in _evidence_text(run_dir / "patch.diff").splitlines():
        match = re.match(r"diff --git a/(.+) b/(.+)$", line)
        if match and match.group(2) not in paths:
            paths.append(match.group(2))
    return paths


def _evidence_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _verification_failure_reason(result: subprocess.CompletedProcess[str]) -> str | None:
    if result.returncode == 0:
        return None
    output = f"{result.stdout}\n{result.stderr}"
    match = re.search(r"(?:Reason:|ERROR:)\s*([^\s]+)", output)
    return match.group(1) if match else "target_verification_failed"


def _next_allowed_actions(run_status: str, verification_result: str) -> list[str]:
    if run_status == "FAILED":
        return ["inspect_details", "retry_later"]
    if verification_result == "PASS":
        return ["inspect_details", "prepare_review"]
    if verification_result == "FAIL":
        return ["inspect_details", "retry_later"]
    return ["verify", "inspect_details"]
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
            if parsed.path.startswith("/api/runs/"):
                self._handle_summary(parsed.path)
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/approve":
                self._handle_approve()
                return
            if parsed.path == "/api/run":
                self._handle_run()
                return
            if parsed.path == "/api/retry":
                self._handle_retry()
                return
            if parsed.path == "/api/verify":
                self._handle_verify()
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

        def _handle_run(self) -> None:
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                if content_length < 1 or content_length > 1_000_000:
                    raise WorkbenchExecutionError("invalid_execution_request")
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                captured_run = workbench.execute_confirmed_delegation(payload)
            except (UnicodeDecodeError, ValueError, WorkbenchExecutionError) as error:
                self._write_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
                return

            self._write_json(asdict(captured_run), HTTPStatus.CREATED)

        def _handle_retry(self) -> None:
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                if content_length < 1 or content_length > 1_000_000:
                    raise WorkbenchExecutionError("invalid_retry_request")
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                captured_run = workbench.retry_confirmed_delegation(payload)
            except (UnicodeDecodeError, ValueError, WorkbenchExecutionError) as error:
                self._write_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
                return

            self._write_json(asdict(captured_run), HTTPStatus.CREATED)

        def _handle_summary(self, path: str) -> None:
            match = re.fullmatch(r"/api/runs/([0-9]{8}-[0-9]{6}-[0-9]+)(/details)?", path)
            if not match:
                self._write_json({"error": "invalid_captured_run_reference"}, HTTPStatus.BAD_REQUEST)
                return
            try:
                if match.group(2):
                    payload = asdict(workbench.evidence_details_for_captured_run(match.group(1)))
                else:
                    payload = asdict(workbench.summary_for_captured_run(match.group(1)))
            except WorkbenchVerificationError as error:
                self._write_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
                return
            self._write_json(payload)

        def _handle_verify(self) -> None:
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                if content_length < 1 or content_length > 1_000_000:
                    raise WorkbenchVerificationError("invalid_verification_request")
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                summary = workbench.verify_captured_run(payload)
            except (UnicodeDecodeError, ValueError, WorkbenchVerificationError) as error:
                self._write_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
                return
            self._write_json(asdict(summary), HTTPStatus.CREATED)
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
    .approval, .execution {
      border-top: 1px solid var(--line);
      margin-top: 24px;
      padding-top: 20px;
    }
    .approval label, .execution label {
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
        <div id="execution" class="execution hidden">
          <div class="meta">Starting a run invokes only the approved target-mode adapter task. It captures run evidence but does not verify or promote it.</div>
          <label for="execution-confirmation"><input id="execution-confirmation" type="checkbox">I confirm that I want to start this approved target-mode delegation now.</label>
          <button id="run-button" type="button">Run Approved Delegation</button>
          <div id="execution-result" class="approved hidden"></div>
          <div id="evidence-summary" class="hidden"></div>
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
    const execution = document.querySelector("#execution");
    const executionConfirmation = document.querySelector("#execution-confirmation");
    const executionResult = document.querySelector("#execution-result");
    const runButton = document.querySelector("#run-button");
    const evidenceSummary = document.querySelector("#evidence-summary");
    const retryAdapters = ["codex", "claude-code", "copilot", "opencode", "cursor", "kiro", "qoder", "kilo", "antigravity"];
    let loadedIssue = null;
    let approvedDelegation = null;

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
      approvedDelegation = null;
      executionConfirmation.checked = false;
      execution.classList.add("hidden");
      executionResult.classList.add("hidden");
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
        approvedDelegation = payload;
        executionConfirmation.checked = false;
        executionResult.classList.add("hidden");
        execution.classList.remove("hidden");
      } catch (approvalError) {
        error.textContent = approvalError.message;
        error.classList.remove("hidden");
      } finally {
        approveButton.disabled = false;
      }
    });

    runButton.addEventListener("click", async () => {
      error.classList.add("hidden");
      executionResult.classList.add("hidden");
      if (!approvedDelegation) {
        error.textContent = "missing_approved_delegation";
        error.classList.remove("hidden");
        return;
      }

      runButton.disabled = true;
      try {
        const response = await fetch("/api/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            task_file: approvedDelegation.task_file,
            confirmed: executionConfirmation.checked,
          }),
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error || "target_mode_run_failed");
        }
        const failure = payload.failure_reason ? ` (${payload.failure_reason})` : "";
        executionResult.textContent = `Captured run ${payload.run_id}: ${payload.run_status}${failure}.`;
        executionResult.classList.remove("hidden");
        await renderEvidenceSummary(payload.run_id);
      } catch (executionError) {
        error.textContent = executionError.message;
        error.classList.remove("hidden");
      } finally {
        runButton.disabled = false;
      }
    });
    async function renderEvidenceSummary(runId, verify = false) {
      const response = await fetch(verify ? "/api/verify" : `/api/runs/${runId}`, {
        method: verify ? "POST" : "GET",
        headers: verify ? { "Content-Type": "application/json" } : undefined,
        body: verify ? JSON.stringify({ run_id: runId }) : undefined,
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "evidence_summary_failed");
      }
      evidenceSummary.replaceChildren();
      const heading = document.createElement("h3");
      heading.textContent = `Operator evidence summary: ${payload.run_id}`;
      evidenceSummary.append(heading);
      const fields = [
        ["Task intent", payload.task_intent],
        ["Approved scope", (payload.approved_scope || []).join(", ") || "missing"],
        ["Adapter", payload.adapter],
        ["Run status", payload.run_status],
        ["Changed paths", (payload.changed_paths || []).join(", ") || "none"],
        ["Verification", payload.verification_result],
        ["Acceptance", payload.acceptance_result],
        ["Failure reason", payload.failure_reason || payload.verification_reason || "none"],
        ["Next allowed actions", (payload.next_allowed_actions || []).join(", ")],
      ];
      const list = document.createElement("dl");
      fields.forEach(([label, value]) => {
        const term = document.createElement("dt");
        term.textContent = label;
        const detail = document.createElement("dd");
        detail.textContent = value;
        list.append(term, detail);
      });
      evidenceSummary.append(list);
      if (payload.verification_result === "NOT_RUN" && payload.run_status === "COMPLETED") {
        const verifyButton = document.createElement("button");
        verifyButton.type = "button";
        verifyButton.textContent = "Verify Captured Run";
        verifyButton.addEventListener("click", async () => {
          verifyButton.disabled = true;
          try {
            await renderEvidenceSummary(runId, true);
          } catch (verificationError) {
            error.textContent = verificationError.message;
            error.classList.remove("hidden");
          }
        });
        evidenceSummary.append(verifyButton);
      }
      if (payload.run_status === "FAILED" || payload.verification_result === "FAIL") {
        const retry = document.createElement("div");
        retry.className = "execution";
        const retryNote = document.createElement("div");
        retryNote.className = "meta";
        retryNote.textContent = "Retry creates a new captured run from this run's recorded approved task and scope. It does not change the failed evidence.";
        const retryLabel = document.createElement("label");
        retryLabel.textContent = "Retry adapter";
        const retryAdapter = document.createElement("select");
        retryAdapters.forEach((adapter) => {
          const option = document.createElement("option");
          option.value = adapter;
          option.textContent = adapter;
          option.selected = adapter === payload.adapter;
          retryAdapter.append(option);
        });
        if (!retryAdapters.includes(payload.adapter)) retryAdapter.value = retryAdapters[0];
        const retryConfirmationLabel = document.createElement("label");
        const retryConfirmation = document.createElement("input");
        retryConfirmation.type = "checkbox";
        retryConfirmationLabel.append(retryConfirmation, "I confirm that I want to retry this approved task now.");
        const retryButton = document.createElement("button");
        retryButton.type = "button";
        retryButton.textContent = "Retry Approved Task";
        retryButton.addEventListener("click", async () => {
          error.classList.add("hidden");
          retryButton.disabled = true;
          try {
            const failedEvidenceSummary = evidenceSummary.cloneNode(true);
            const retryResponse = await fetch("/api/retry", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                run_id: runId,
                adapter: retryAdapter.value,
                confirmed: retryConfirmation.checked,
              }),
            });
            const retryPayload = await retryResponse.json();
            if (!retryResponse.ok) {
              throw new Error(retryPayload.error || "retry_failed");
            }
            await renderEvidenceSummary(retryPayload.run_id);
            const priorEvidence = document.createElement("details");
            priorEvidence.open = true;
            const priorEvidenceTitle = document.createElement("summary");
            priorEvidenceTitle.textContent = `Prior failed evidence summary: ${runId}`;
            priorEvidence.append(priorEvidenceTitle, failedEvidenceSummary);
            evidenceSummary.prepend(priorEvidence);
          } catch (retryError) {
            error.textContent = retryError.message;
            error.classList.remove("hidden");
          } finally {
            retryButton.disabled = false;
          }
        });
        retry.append(retryNote, retryLabel, retryAdapter, retryConfirmationLabel, retryButton);
        evidenceSummary.append(retry);
      }
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = "Raw stdout, stderr, and patch diff";
      details.append(summary);
      details.addEventListener("toggle", async () => {
        if (!details.open || details.dataset.loaded) return;
        const detailResponse = await fetch(`/api/runs/${runId}/details`);
        const raw = await detailResponse.json();
        if (!detailResponse.ok) return;
        [["stdout", raw.stdout], ["stderr", raw.stderr], ["patch diff", raw.patch_diff]].forEach(([label, text]) => {
          const title = document.createElement("h4");
          title.textContent = label;
          const pre = document.createElement("pre");
          pre.textContent = text || "missing";
          details.append(title, pre);
        });
        details.dataset.loaded = "true";
      });
      evidenceSummary.append(details);
      evidenceSummary.classList.remove("hidden");
    }
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
