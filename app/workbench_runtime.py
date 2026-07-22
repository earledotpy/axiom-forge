from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock

from forge.committed_evidence import CommittedEvidenceError, read_committed_file
from forge.git import run_git
from scripts.delegation_artifact_set import (
    DelegationArtifactSetError, acceptance_check_path, load_task_artifact_set,
    scope_sidecar_path, validate_delegation_task_file,
)
from scripts.operator_evidence import summarize_run
from scripts.target_task_scope import TargetTaskScopeError, validate_scope_path

from app.workbench_drafts import issue_to_draft_preview, parse_issue_reference
from app.planning_sessions import PlanningSessionError, PlanningSessionStore
from app.workbench_models import (
    DEFAULT_ADAPTERS, ApprovedDelegation, CapturedRun, ConfirmedExecution, ConfirmedRetry,
    DraftTaskPreview, HistoricalCapturedRun, IssueFetcher, OperatorDecisionQueue,
    OperatorDecisionQueueItem, OperatorDecisionQueueStage, OperatorEvidenceDetails,
    OperatorEvidenceSummary, PromotionResult, PromotionReviewPreparation, PromotionReviewSubmission,
    TargetRunner, VerificationRunner, WorkbenchApprovalError, WorkbenchExecutionError,
    WorkbenchPromotionError, WorkbenchPromotionReviewError, WorkbenchVerificationError,
)

class WorkbenchServer:
    def __init__(
        self,
        issue_fetcher: IssueFetcher,
        default_repo: str | None = None,
        forge_root: Path | None = None,
        target_runner: TargetRunner | None = None,
        verification_runner: VerificationRunner | None = None,
        planning_sessions: PlanningSessionStore | None = None,
    ):
        self.issue_fetcher = issue_fetcher
        self.default_repo = default_repo
        self.forge_root = (forge_root or Path.cwd()).resolve()
        self._target_runner = target_runner or _run_target_mode_runner
        self._verification_runner = verification_runner or _run_target_mode_verifier
        self._operation_lock = Lock()
        self._active_delegation_lock = Lock()
        self._active_delegation: tuple[str, str] | None = None
        self._active_promotion_lock = Lock()
        self._active_promotion: str | None = None
        self.planning_sessions = planning_sessions

    def start_planning_session(self, payload: object) -> dict:
        if not isinstance(payload, dict):
            raise PlanningSessionError("invalid_planning_session_request")
        request = dict(payload)
        issue_seed = request.get("issue_seed")
        if issue_seed is not None:
            if not isinstance(issue_seed, str):
                raise PlanningSessionError("invalid_planning_issue_seed")
            try:
                reference = parse_issue_reference(issue_seed, default_repo=self.default_repo)
                issue = self.issue_fetcher(reference)
            except (RuntimeError, ValueError) as error:
                raise PlanningSessionError("planning_issue_seed_fetch_failed") from error
            request["issue_seed"] = asdict(issue)
        return self._planning_sessions().start(request)

    def planning_session(self, session_id: str) -> dict:
        return self._planning_sessions().session(session_id)

    def planning_sessions_list(self) -> list[dict]:
        return self._planning_sessions().list_sessions()

    def send_planning_message(self, session_id: str, payload: object) -> dict:
        if not isinstance(payload, dict) or set(payload) != {"message"}:
            raise PlanningSessionError("invalid_planning_message")
        return self._planning_sessions().send(session_id, payload["message"])

    def close_planning_session(self, session_id: str) -> dict:
        return self._planning_sessions().close(session_id)

    def planning_proposal_for_approval(self, session_id: str, version: int) -> dict:
        return self._planning_sessions().proposal_for_approval(session_id, version)

    def _planning_sessions(self) -> PlanningSessionStore:
        if self.planning_sessions is None:
            raise PlanningSessionError("planning_sessions_unavailable")
        return self.planning_sessions
    def preview_for_issue(self, raw_reference: str) -> DraftTaskPreview:
        reference = parse_issue_reference(raw_reference, default_repo=self.default_repo)
        issue = self.issue_fetcher(reference)
        return issue_to_draft_preview(issue)

    def approve_draft(self, payload: object) -> ApprovedDelegation:
        approval = _parse_approval(payload)
        proposal_sha256 = None
        if approval.planning_session_id is not None:
            try:
                proposal = self._planning_sessions().proposal_for_approval(
                    approval.planning_session_id,
                    approval.planning_proposal_version,
                )
            except PlanningSessionError as error:
                raise WorkbenchApprovalError(str(error)) from error
            proposal_sha256 = proposal["proposal_sha256"]
        task_file = self.forge_root / "tasks" / f"workbench-issue-{approval.issue_number}.task.md"
        scope_file = scope_sidecar_path(task_file)
        acceptance_file = acceptance_check_path(task_file)

        _validate_approval(approval, task_file, acceptance_file)
        _require_clean_forge_repo(self.forge_root)
        if any(path.exists() for path in (task_file, scope_file, acceptance_file)):
            raise WorkbenchApprovalError("delegation_artifact_already_exists")

        task_file.parent.mkdir(parents=True, exist_ok=True)
        task_file.write_text(
            _approved_task_text(
                approval.task_text,
                approval.adapter,
                planning_session_id=approval.planning_session_id,
                planning_proposal_sha256=proposal_sha256,
            ),
            encoding="utf-8",
        )
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
            planning_session_id=approval.planning_session_id,
            planning_proposal_sha256=proposal_sha256,
        )

    def execute_confirmed_delegation(self, payload: object) -> CapturedRun:
        execution = _parse_confirmed_execution(payload)
        _, adapter = _approved_execution_target(self.forge_root, execution.task_file)
        return self._run_confirmed_delegation(execution.task_file, adapter)

    def retry_confirmed_delegation(self, payload: object) -> CapturedRun:
        retry = _parse_confirmed_retry(payload)
        task_file = _retry_execution_target(self.forge_root, retry.run_id)
        return self._run_confirmed_delegation(task_file, retry.adapter)

    def prepare_promotion_review(self, payload: object) -> PromotionReviewPreparation:
        run_id = _parse_promotion_run_request(payload, "invalid_promotion_review_request")
        run_dir = _captured_run_directory(self.forge_root, run_id)
        evidence = _run_evidence(self.forge_root, run_dir)
        if evidence["state"] != "verified":
            raise WorkbenchPromotionReviewError("captured_run_not_awaiting_promotion_review")
        record = _evidence_json(run_dir / "record.json")
        patch_sha256 = record.get("patch_sha256")
        if not isinstance(patch_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", patch_sha256):
            raise WorkbenchPromotionReviewError("promotion_review_patch_identity_unavailable")
        reviewer_hint = _git_config_value(self.forge_root, "user.name")
        email = _git_config_value(self.forge_root, "user.email")
        if reviewer_hint and email:
            reviewer_hint = f"{reviewer_hint} <{email}>"
        problems = []
        if evidence["target"]["stale_base"]:
            problems.append("stale_delegation_target_base")
        current_base_problem = _current_target_base_problem(evidence)
        if current_base_problem is not None and current_base_problem not in problems:
            problems.append(current_base_problem)
        return PromotionReviewPreparation("promotion_review_preparation", run_id, patch_sha256, _task_intent_from_evidence(run_dir), evidence["evidence_revisions"]["delegation_artifact_revision"], evidence["task"]["approved_paths"], evidence["run"]["adapter"] or "missing_adapter", evidence["target"], evidence["patch"]["changed_paths"], _evidence_text(run_dir / "patch.diff"), evidence["verification"], evidence["acceptance"]["status"], problems, reviewer_hint)

    def submit_promotion_review(self, payload: object) -> PromotionReviewSubmission:
        request = _parse_promotion_review_submission(payload)
        run_dir = _captured_run_directory(self.forge_root, request["run_id"])
        path = self.forge_root / "reviews" / "promotion" / f"{request['run_id']}.json"
        _require_clean_promotion_review_repo(self.forge_root)
        if path.exists() or run_git(self.forge_root, "cat-file", "-e", f"HEAD:{path.relative_to(self.forge_root).as_posix()}").returncode == 0:
            raise WorkbenchPromotionReviewError("promotion_review_already_exists")
        preparation = self.prepare_promotion_review({"run_id": request["run_id"]})
        if request["patch_sha256"] != preparation.patch_sha256:
            raise WorkbenchPromotionReviewError("promotion_review_patch_mismatch")
        if request["decision"] == "APPROVED" and preparation.evidence_problems:
            raise WorkbenchPromotionReviewError(preparation.evidence_problems[0])
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {"schema_version": 1, "review_type": "promotion", **request}
        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        repo_path = path.relative_to(self.forge_root).as_posix()
        try:
            _run_git_review(self.forge_root, ["add", "--", repo_path], "promotion_review_stage_failed")
            _run_git_review(self.forge_root, ["commit", "-m", f"Record promotion review for {request['run_id']}"], "promotion_review_commit_failed")
        except Exception:
            run_git(self.forge_root, "restore", "--staged", "--", repo_path)
            path.unlink(missing_ok=True)
            raise
        revision = _git_output_review(self.forge_root, ["rev-parse", "HEAD"], "promotion_review_revision_unresolved")
        return PromotionReviewSubmission("promotion_review_submission", request["run_id"], request["decision"], revision)

    def confirm_promotion(self, payload: object) -> PromotionResult:
        run_id = _parse_promotion_confirmation(payload)
        with self._operation_lock:
            if self._active_delegation is not None:
                raise WorkbenchPromotionError("active_workbench_delegation_in_progress")
            if self._active_promotion is not None:
                raise WorkbenchPromotionError("active_promotion_in_progress")
            self._active_promotion = run_id
        try:
            with self._active_delegation_lock:
                if self._active_delegation is not None:
                    raise WorkbenchPromotionError("active_workbench_delegation_in_progress")
            run_dir = _captured_run_directory(self.forge_root, run_id)
            record = _evidence_json(run_dir / "record.json")
            command = ["bash", str(self.forge_root / "scripts" / "promote.sh")]
            if record.get("run_mode") == "target":
                command.append("--target")
            command.append(run_dir.relative_to(self.forge_root).as_posix())
            result = subprocess.run(command, cwd=self.forge_root, text=True, input=run_id + "\n", capture_output=True, check=False)
            promotion = _evidence_json(run_dir / "promotion.json")
            state = "promoted" if promotion.get("status") == "PROMOTED" else "failed"
            reason = promotion.get("reason") if isinstance(promotion.get("reason"), str) else "promotion_failed"
            diagnostics = _bounded_promotion_diagnostics(result.stdout, result.stderr)
            return PromotionResult("promotion", run_id, state, reason, promotion.get("branch") if isinstance(promotion.get("branch"), str) else None, promotion.get("promotion_commit") if isinstance(promotion.get("promotion_commit"), str) else None, promotion.get("promotion_review_revision") if isinstance(promotion.get("promotion_review_revision"), str) else None, promotion, diagnostics)
        except WorkbenchVerificationError as error:
            raise WorkbenchPromotionError(str(error)) from error
        finally:
            with self._operation_lock:
                self._active_promotion = None
    def live_run(self) -> dict:
        state_path = self.forge_root / "runs" / ".live-run.json"
        if not state_path.is_file():
            with self._active_delegation_lock:
                active = self._active_delegation is not None
            if active:
                return _live_run_unavailable("live_run_state_missing")
            return {"authority": "live_run_stream", "state": "inactive"}
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            run_id, lifecycle_state = _live_run_identity(state)
            if lifecycle_state == "terminal":
                return {
                    "authority": "live_run_stream",
                    "state": "terminal",
                    "run_id": run_id,
                }
            stdout_path = _live_run_log_path(self.forge_root, state, run_id, "stdout")
            stderr_path = _live_run_log_path(self.forge_root, state, run_id, "stderr")
            return {
                "authority": "live_run_stream",
                "state": "active",
                "run_id": run_id,
                "stdout": _bounded_live_tail(stdout_path),
                "stderr": _bounded_live_tail(stderr_path),
            }
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return _live_run_unavailable("live_run_state_invalid")

    def _run_confirmed_delegation(self, task_file: str, adapter: str) -> CapturedRun:
        command = [
            "bash",
            str(self.forge_root / "scripts" / "run_agent_task.sh"),
            "--target",
            adapter,
            task_file,
        ]
        with self._operation_lock:
            if self._active_promotion is not None:
                raise WorkbenchExecutionError("active_promotion_in_progress")
            if self._active_delegation:
                raise WorkbenchExecutionError("active_workbench_delegation_in_progress")
            self._active_delegation = (task_file, adapter)
        try:
            result = self._target_runner(command, self.forge_root)
        except OSError as error:
            raise WorkbenchExecutionError("target_mode_runner_start_failed") from error
        finally:
            with self._operation_lock:
                self._active_delegation = None

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
        return _summary_from_evidence(
            _run_evidence(self.forge_root, run_dir),
            run_dir,
            verification_failure_reason=_verification_failure_reason(result),
        )

    def summary_for_captured_run(self, run_id: str) -> OperatorEvidenceSummary:
        run_dir = _captured_run_directory(self.forge_root, run_id)
        return _summary_from_evidence(_run_evidence(self.forge_root, run_dir), run_dir)

    def historical_captured_runs(self) -> list[HistoricalCapturedRun]:
        runs_root = self.forge_root / "runs"
        if not runs_root.is_dir():
            return []
        return [
            _historical_captured_run(self.forge_root, run_dir)
            for run_dir in sorted(runs_root.iterdir(), key=lambda path: path.name, reverse=True)
            if run_dir.is_dir() and _is_captured_run_id(run_dir.name)
        ]

    def operator_decision_queue(self) -> OperatorDecisionQueue:
        history = self.historical_captured_runs()
        planning_proposals = self._planning_proposal_queue_items()
        with self._active_delegation_lock:
            active_delegation = self._active_delegation

        active_task_file = active_delegation[0] if active_delegation else None
        represented_task_files = {
            task_file
            for run in history
            if run.state != "superseded"
            for task_file in [_delegation_task_file(self.forge_root, run.run_id)]
            if task_file is not None
        }
        awaiting_execution = [
            _awaiting_execution_queue_item(self.forge_root, task_file)
            for task_file in _delegation_ready_task_files(self.forge_root)
            if task_file not in represented_task_files and task_file != active_task_file
        ]
        executing = (
            [_executing_queue_item(*active_delegation)]
            if active_delegation is not None
            else []
        )
        awaiting_verification: list[OperatorDecisionQueueItem] = []
        awaiting_promotion_review: list[OperatorDecisionQueueItem] = []
        awaiting_promotion: list[OperatorDecisionQueueItem] = []
        retry_decision: list[OperatorDecisionQueueItem] = []
        evidence_problems: list[OperatorDecisionQueueItem] = []

        for run in history:
            if run.state == "superseded":
                continue
            if run.summary is None:
                evidence_problems.append(_evidence_problem_queue_item(run))
                continue
            summary = run.summary
            task_file = _delegation_task_file(self.forge_root, run.run_id)
            if summary.run_status not in {"COMPLETED", "FAILED"}:
                evidence_problems.append(_invalid_evidence_queue_item(run))
            elif summary.run_status == "FAILED" or summary.verification_result == "FAIL":
                retry_decision.append(_retry_queue_item(summary, task_file))
            elif summary.verification_result == "NOT_RUN":
                awaiting_verification.append(_verification_queue_item(summary, task_file))
            elif summary.verification_result == "PASS" and run.state == "verified":
                awaiting_promotion_review.append(_promotion_review_queue_item(summary, task_file))
            elif run.state == "promotion-ready":
                awaiting_promotion.append(_promotion_queue_item(self.forge_root, summary, task_file))

        return OperatorDecisionQueue(
            authority="operator_decision_queue",
            stages=[
                OperatorDecisionQueueStage(
                    "planning_proposals",
                    "Planning proposals awaiting approval",
                    planning_proposals,
                ),
                OperatorDecisionQueueStage("awaiting_execution", "Awaiting execution", awaiting_execution),
                OperatorDecisionQueueStage("executing", "Executing", executing),
                OperatorDecisionQueueStage("awaiting_verification", "Awaiting verification", awaiting_verification),
                OperatorDecisionQueueStage(
                    "awaiting_promotion_review",
                    "Verified, awaiting promotion review",
                    awaiting_promotion_review,
                ),
                OperatorDecisionQueueStage("awaiting_promotion", "Promotion-ready, awaiting promotion", awaiting_promotion),
                OperatorDecisionQueueStage("retry_decision", "Retry decision", retry_decision),
                OperatorDecisionQueueStage("evidence_problems", "Evidence problems", evidence_problems),
            ],
        )

    def _planning_proposal_queue_items(self) -> list[OperatorDecisionQueueItem]:
        if self.planning_sessions is None:
            return []
        items = []
        for session in self.planning_sessions.list_sessions():
            if session["state"] in {"FAILED", "BOUNDARY_VIOLATION"}:
                continue
            valid = [proposal for proposal in session["proposals"] if proposal.get("valid") is True]
            if not valid:
                continue
            proposal = valid[-1]
            items.append(OperatorDecisionQueueItem(
                stage="planning_proposals",
                decision_label="Review planning proposal",
                evidence_line=(
                    f"{session['adapter']} · session {session['session_id'][:8]} · "
                    f"proposal {proposal['version']} · draft-only"
                ),
                action_label="Review proposal →",
                action="review_planning_proposal",
                run_id=None,
                task_file=None,
                adapter=proposal["proposal"]["suggested_adapter"],
                run_status=None,
                verification_result=None,
                acceptance_result=None,
                changed_paths=proposal["proposal"]["target_scope"],
                failure_reason=None,
                evidence_error=None,
                planning_session_id=session["session_id"],
                planning_proposal_version=proposal["version"],
            ))
        return items

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
    planning_session_id: str | None
    planning_proposal_version: int


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

    planning_session_id = payload.get("planning_session_id")
    planning_proposal_version = payload.get("planning_proposal_version")
    if planning_session_id is None and planning_proposal_version is None:
        planning_proposal_version = 0
    elif (
        not isinstance(planning_session_id, str)
        or not re.fullmatch(r"[a-f0-9]{32}", planning_session_id)
        or not isinstance(planning_proposal_version, int)
        or isinstance(planning_proposal_version, bool)
        or planning_proposal_version < 1
    ):
        raise WorkbenchApprovalError("invalid_planning_proposal_reference")

    return DraftApproval(
        issue_number=issue_number,
        task_text=payload["task_text"],
        target_scope=payload["target_scope"],
        acceptance_check=payload["acceptance_check"],
        adapter=payload["adapter"],
        planning_session_id=planning_session_id,
        planning_proposal_version=planning_proposal_version,
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
        summary = _summary_from_evidence(_run_evidence(root, run_dir), run_dir)
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
    try:
        return read_committed_file(
            root,
            revision,
            repo_path,
            missing_reason="retry_delegation_provenance_unavailable",
            encoding="utf-8",
        )
    except CommittedEvidenceError as exc:
        raise WorkbenchExecutionError(exc.reason) from exc

def _run_target_mode_runner(command: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=root, text=True, capture_output=True, check=False)


_RUNNER_DIAGNOSTIC_TAIL_LIMIT = 1900


def _environment_secret_values() -> list[str]:
    markers = ("TOKEN", "SECRET", "PASSWORD", "API_KEY")
    return [
        value
        for name, value in os.environ.items()
        if any(marker in name.upper() for marker in markers) and value
    ]


def _runner_diagnostic_tail(result: subprocess.CompletedProcess[str]) -> str:
    output = result.stderr or result.stdout or ""
    for secret in _environment_secret_values():
        output = output.replace(secret, "[REDACTED]")
    scrubbed = re.sub(
        r'(?im)(["\']?[\w.-]*(?:token|secret|password|api[_-]?key)[\w.-]*["\']?\s*[:=]\s*)(?:"[^"]*"|\'[^\']*\'|[^\r\n]*)',
        r"\1[REDACTED]",
        output,
    )
    scrubbed = re.sub(r'(?im)(["\']?authorization["\']?\s*[:=]\s*)(?:"[^"]*"|\'[^\']*\'|[^\r\n]*)', r"\1[REDACTED]", scrubbed)
    if len(scrubbed) > _RUNNER_DIAGNOSTIC_TAIL_LIMIT:
        return "...[truncated]\n" + scrubbed[-_RUNNER_DIAGNOSTIC_TAIL_LIMIT:]
    return scrubbed


def _captured_run_from_runner_result(
    root: Path, result: subprocess.CompletedProcess[str]
) -> CapturedRun:
    output = f"{result.stdout}\n{result.stderr}"
    match = re.search(r"^RUN_(?:CAPTURED|FAILED): ([0-9]{8}-[0-9]{6}-[0-9]+)$", output, re.MULTILINE)
    if not match:
        diagnostic = _runner_diagnostic_tail(result)
        reason = "target_mode_runner_did_not_capture_run"
        raise WorkbenchExecutionError(f"{reason}: {diagnostic}" if diagnostic else reason)

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

def _parse_promotion_run_request(payload: object, reason: str) -> str:
    if not isinstance(payload, dict) or set(payload) != {"run_id"}:
        raise WorkbenchPromotionReviewError(reason)
    run_id = payload.get("run_id")
    if not isinstance(run_id, str) or not _is_captured_run_id(run_id):
        raise WorkbenchPromotionReviewError("invalid_captured_run_reference")
    return run_id


def _parse_promotion_review_submission(payload: object) -> dict[str, object]:
    required = {"run_id", "patch_sha256", "reviewer", "decision", "concerns", "follow_up_tasks", "evidence_attestation"}
    if not isinstance(payload, dict) or set(payload) != required:
        raise WorkbenchPromotionReviewError("invalid_promotion_review_submission")
    run_id = payload["run_id"]
    patch = payload["patch_sha256"]
    reviewer = payload["reviewer"]
    decision = payload["decision"]
    concerns = payload["concerns"]
    followups = payload["follow_up_tasks"]
    if not isinstance(run_id, str) or not _is_captured_run_id(run_id) or not isinstance(patch, str) or not re.fullmatch(r"[0-9a-f]{64}", patch):
        raise WorkbenchPromotionReviewError("invalid_promotion_review_identity")
    if not isinstance(reviewer, str) or not reviewer.strip() or not isinstance(concerns, str) or not concerns.strip() or payload["evidence_attestation"] is not True:
        raise WorkbenchPromotionReviewError("invalid_promotion_review_attestation")
    if decision not in {"APPROVED", "CHANGES_REQUESTED"}:
        raise WorkbenchPromotionReviewError("invalid_promotion_review_decision")
    if not isinstance(followups, list):
        raise WorkbenchPromotionReviewError("invalid_promotion_review_followups")
    if decision == "APPROVED" and followups:
        raise WorkbenchPromotionReviewError("approved_promotion_review_has_followups")
    if decision == "CHANGES_REQUESTED":
        if concerns.strip() == "NO_CONCERNS" or not followups:
            raise WorkbenchPromotionReviewError("changes_requested_followups_required")
        for task in followups:
            if not isinstance(task, dict) or task.get("kind") != "bounded_patch_task":
                raise WorkbenchPromotionReviewError("issue_anchored_followups_required")
            required_task_fields = ("task_file", "task_text", "target_scope", "acceptance_check", "adapter", "issue_reference")
            if any(not isinstance(task.get(field), str) or not task[field].strip() for field in required_task_fields):
                raise WorkbenchPromotionReviewError("issue_anchored_followups_required")
            if not re.fullmatch(r"https://github.com/[^/]+/[^/]+/issues/[1-9][0-9]*", task["issue_reference"]):
                raise WorkbenchPromotionReviewError("issue_anchored_followups_required")
    return dict(payload)


def _parse_promotion_confirmation(payload: object) -> str:
    if not isinstance(payload, dict) or set(payload) != {"run_id", "confirmation"}:
        raise WorkbenchPromotionError("invalid_promotion_confirmation")
    run_id = payload.get("run_id")
    if not isinstance(run_id, str) or not _is_captured_run_id(run_id):
        raise WorkbenchPromotionError("invalid_captured_run_reference")
    if payload.get("confirmation") != run_id:
        raise WorkbenchPromotionError("exact_promotion_confirmation_required")
    return run_id


def _require_clean_promotion_review_repo(root: Path) -> None:
    if run_git(root, "status", "--porcelain").stdout.strip():
        raise WorkbenchPromotionReviewError("forge_repo_dirty")


def _current_target_base_problem(evidence: dict) -> str | None:
    target = evidence.get("target", {})
    repo, branch, recorded_base = target.get("repo"), target.get("base_branch"), target.get("delegation_target_base_sha")
    if not any((repo, branch, recorded_base)):
        return None
    if not all(isinstance(value, str) and value for value in (repo, branch, recorded_base)):
        return "target_identity_unavailable"
    target_root = Path(repo)
    if not target_root.is_dir():
        return "target_identity_unavailable"
    current_branch = run_git(target_root, "branch", "--show-current")
    if current_branch.returncode != 0:
        return "target_branch_unavailable"
    if current_branch.stdout.strip() != branch:
        return "target_not_on_expected_base_branch"
    current_base = run_git(target_root, "rev-parse", f"{branch}^{{commit}}")
    if current_base.returncode != 0:
        return "target_base_sha_unresolved"
    return None if current_base.stdout.strip() == recorded_base else "stale_delegation_target_base"


def _bounded_promotion_diagnostics(stdout: str, stderr: str) -> str:
    output = "\n".join(part for part in (stdout.strip(), stderr.strip()) if part)
    return output[-(8 * 1024):]


def _git_config_value(root: Path, key: str) -> str | None:
    result = run_git(root, "config", "--get", key)
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def _git_output_review(root: Path, args: list[str], reason: str) -> str:
    result = run_git(root, *args)
    if result.returncode != 0:
        raise WorkbenchPromotionReviewError(reason)
    return result.stdout.strip()


def _run_git_review(root: Path, args: list[str], reason: str) -> None:
    _git_output_review(root, args, reason)

def _parse_verification_request(payload: object) -> str:
    if not isinstance(payload, dict) or set(payload) != {"run_id"}:
        raise WorkbenchVerificationError("invalid_verification_request")
    run_id = payload.get("run_id")
    if not isinstance(run_id, str) or not _is_captured_run_id(run_id):
        raise WorkbenchVerificationError("invalid_captured_run_reference")
    return run_id


def _is_captured_run_id(run_id: str) -> bool:
    return re.fullmatch(r"[0-9]{8}-[0-9]{6}-[0-9]+", run_id) is not None


def _live_run_unavailable(reason: str) -> dict:
    return {"authority": "live_run_stream", "state": "unavailable", "reason": reason}


def _live_run_identity(state: object) -> tuple[str, str]:
    if not isinstance(state, dict) or state.get("schema_version") != 1:
        raise ValueError("invalid_live_run_state")
    run_id = state.get("run_id")
    lifecycle_state = state.get("lifecycle_state")
    if not isinstance(run_id, str) or not _is_captured_run_id(run_id):
        raise ValueError("invalid_live_run_state")
    if lifecycle_state not in {"active", "terminal"}:
        raise ValueError("invalid_live_run_state")
    return run_id, lifecycle_state


def _live_run_log_path(root: Path, state: dict, run_id: str, stream: str) -> Path:
    path_value = state.get(f"{stream}_log")
    expected = f"runs/{run_id}/{stream}.log"
    if path_value != expected:
        raise ValueError("invalid_live_run_log_path")
    path = root / path_value
    try:
        path.resolve().relative_to((root / "runs").resolve())
    except ValueError as error:
        raise ValueError("invalid_live_run_log_path") from error
    if not path.is_file():
        raise ValueError("live_run_log_unavailable")
    return path


def _bounded_live_tail(path: Path) -> dict:
    byte_limit = 64 * 1024
    with path.open("rb") as stream:
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(max(0, size - byte_limit))
        tail = stream.read(byte_limit)
    return {"text": tail.decode("utf-8", errors="replace"), "truncated": size > byte_limit}


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


def _run_evidence(forge_root: Path, run_dir: Path) -> dict:
    try:
        record = json.loads((run_dir / "record.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WorkbenchVerificationError("captured_run_record_unavailable") from error
    if not isinstance(record, dict) or record.get("run_id") != run_dir.name:
        raise WorkbenchVerificationError("captured_run_record_invalid")
    return summarize_run(run_dir, forge_root)


def _summary_from_evidence(
    evidence: dict, run_dir: Path, verification_failure_reason: str | None = None
) -> OperatorEvidenceSummary:
    run_status = evidence["run"]["status"] or "missing_run_status"
    verification_result, verification_reason = _verification_view(
        evidence["verification"], verification_failure_reason
    )
    return OperatorEvidenceSummary(
        authority="operator_evidence_summary",
        run_id=run_dir.name,
        task_intent=_task_intent_from_evidence(run_dir),
        approved_scope=evidence["task"]["approved_paths"],
        adapter=evidence["run"]["adapter"] or "missing_adapter",
        run_status=run_status,
        changed_paths=evidence["patch"]["changed_paths"],
        verification_result=verification_result,
        verification_reason=verification_reason,
        acceptance_result=evidence["acceptance"]["status"],
        failure_reason=evidence["run"]["failure_reason"],
        next_allowed_actions=_next_allowed_actions(run_status, verification_result),
    )


def _verification_view(
    verification: dict, verification_failure_reason: str | None
) -> tuple[str, str | None]:
    status = verification["status"]
    if status == "MISSING":
        if verification_failure_reason is None:
            return "NOT_RUN", None
        return "FAIL", verification_failure_reason
    reason = verification["reason"]
    if not isinstance(reason, str) or not reason:
        reason = verification_failure_reason
    return ("PASS" if status == "PASS" else "FAIL"), reason


def _historical_captured_run(forge_root: Path, run_dir: Path) -> HistoricalCapturedRun:
    try:
        evidence = _run_evidence(forge_root, run_dir)
    except WorkbenchVerificationError as error:
        return HistoricalCapturedRun(
            authority="historical_captured_run",
            run_id=run_dir.name,
            state="missing_evidence",
            verification_state="missing_evidence",
            read_only=True,
            summary=None,
            evidence_error=str(error),
        )

    return HistoricalCapturedRun(
        authority="historical_captured_run",
        run_id=run_dir.name,
        state=evidence["state"],
        verification_state=_historical_verification_state(evidence["verification"]["status"]),
        read_only=True,
        summary=_summary_from_evidence(evidence, run_dir),
        evidence_error=None,
    )


def _delegation_ready_task_files(forge_root: Path) -> list[str]:
    tasks_root = forge_root / "tasks"
    if not tasks_root.is_dir():
        return []
    ready_task_files = []
    for task_path in sorted(tasks_root.rglob("*.task.md")):
        try:
            artifact_set = load_task_artifact_set(task_path)
            task_file = task_path.relative_to(forge_root).as_posix()
        except (DelegationArtifactSetError, ValueError):
            continue
        if artifact_set.state == "delegation-ready" and artifact_set.approved_adapter:
            ready_task_files.append(task_file)
    return ready_task_files


def _delegation_task_file(forge_root: Path, run_id: str) -> str | None:
    record = _evidence_json(forge_root / "runs" / run_id / "record.json")
    task_file = record.get("delegation_task_file")
    return task_file if isinstance(task_file, str) else None


def _awaiting_execution_queue_item(forge_root: Path, task_file: str) -> OperatorDecisionQueueItem:
    artifact_set = load_task_artifact_set(forge_root / task_file)
    adapter = artifact_set.approved_adapter or "missing_adapter"
    return OperatorDecisionQueueItem(
        stage="awaiting_execution",
        decision_label="Execute approved delegation",
        evidence_line=f"{task_file} · {adapter} · delegation-ready",
        action_label="Execute →",
        action="execute",
        run_id=None,
        task_file=task_file,
        adapter=adapter,
        run_status=None,
        verification_result=None,
        acceptance_result=None,
        changed_paths=[],
        failure_reason=None,
        evidence_error=None,
    )


def _executing_queue_item(task_file: str, adapter: str) -> OperatorDecisionQueueItem:
    return OperatorDecisionQueueItem(
        stage="executing",
        decision_label="Delegation is executing",
        evidence_line=f"{task_file} · {adapter} · executing",
        action_label=None,
        action=None,
        run_id=None,
        task_file=task_file,
        adapter=adapter,
        run_status="EXECUTING",
        verification_result=None,
        acceptance_result=None,
        changed_paths=[],
        failure_reason=None,
        evidence_error=None,
    )


def _run_queue_item(
    summary: OperatorEvidenceSummary,
    task_file: str | None,
    *,
    stage: str,
    decision_label: str,
    action_label: str,
    action: str,
    include_review_evidence: bool = False,
    promotion_evidence: dict | None = None,
) -> OperatorDecisionQueueItem:
    fields = [summary.run_id, task_file or "missing_task_file", summary.adapter, summary.run_status]
    if summary.verification_result:
        fields.append(f"verification {summary.verification_result}")
    if include_review_evidence:
        fields.append(f"acceptance {summary.acceptance_result}")
        fields.append(f"changed paths {', '.join(summary.changed_paths) or 'none'}")
    failure_reason = summary.failure_reason or summary.verification_reason
    if failure_reason:
        fields.append(failure_reason)
    review = promotion_evidence or {}
    target = review.get("target", {})
    committed_review = review.get("review", {})
    return OperatorDecisionQueueItem(
        stage=stage,
        decision_label=decision_label,
        evidence_line=" · ".join(fields),
        action_label=action_label,
        action=action,
        run_id=summary.run_id,
        task_file=task_file,
        adapter=summary.adapter,
        run_status=summary.run_status,
        verification_result=summary.verification_result,
        acceptance_result=summary.acceptance_result,
        changed_paths=summary.changed_paths,
        failure_reason=failure_reason,
        evidence_error=None,
        target_repository=target.get("repo"),
        target_branch=target.get("base_branch"),
        target_base_sha=target.get("delegation_target_base_sha"),
        reviewer=committed_review.get("reviewer"),
        review_decision=committed_review.get("decision"),
        review_concerns=committed_review.get("concerns"),
        promotion_review_revision=committed_review.get("revision"),
        current_blocker=review.get("blocker"),
    )


def _verification_queue_item(summary: OperatorEvidenceSummary, task_file: str | None) -> OperatorDecisionQueueItem:
    return _run_queue_item(
        summary,
        task_file,
        stage="awaiting_verification",
        decision_label="Verify captured run",
        action_label="Verify →",
        action="verify",
    )


def _promotion_review_queue_item(summary: OperatorEvidenceSummary, task_file: str | None) -> OperatorDecisionQueueItem:
    return _run_queue_item(
        summary,
        task_file,
        stage="awaiting_promotion_review",
        decision_label="Prepare promotion review",
        action_label="Prepare review →",
        action="prepare_review",
        include_review_evidence=True,
    )


def _promotion_queue_item(forge_root: Path, summary: OperatorEvidenceSummary, task_file: str | None) -> OperatorDecisionQueueItem:
    evidence = summarize_run(forge_root / "runs" / summary.run_id, forge_root)
    review_path = forge_root / "reviews" / "promotion" / f"{summary.run_id}.json"
    review = _evidence_json(review_path) if review_path.is_file() else {}
    review["revision"] = evidence["evidence_revisions"].get("promotion_review_revision")
    blocker = _current_target_base_problem(evidence)
    if blocker is None and run_git(forge_root, "status", "--porcelain").stdout.strip():
        blocker = "forge_repo_dirty"
    return _run_queue_item(
        summary,
        task_file,
        stage="awaiting_promotion",
        decision_label="Promotion-ready, awaiting promotion",
        action_label="Promote…",
        action="promote",
        include_review_evidence=True,
        promotion_evidence={"target": evidence["target"], "review": review, "blocker": blocker},
    )

def _retry_queue_item(summary: OperatorEvidenceSummary, task_file: str | None) -> OperatorDecisionQueueItem:
    return _run_queue_item(
        summary,
        task_file,
        stage="retry_decision",
        decision_label="Choose retry or abandon",
        action_label="Retry with… →",
        action="retry",
    )


def _evidence_problem_queue_item(run: HistoricalCapturedRun) -> OperatorDecisionQueueItem:
    return OperatorDecisionQueueItem(
        stage="evidence_problems",
        decision_label="Resolve evidence problem",
        evidence_line=f"{run.run_id} · {run.evidence_error or 'evidence unavailable'}",
        action_label="Inspect evidence →",
        action="inspect_evidence",
        run_id=run.run_id,
        task_file=None,
        adapter=None,
        run_status=None,
        verification_result=None,
        acceptance_result=None,
        changed_paths=[],
        failure_reason=None,
        evidence_error=run.evidence_error,
    )


def _invalid_evidence_queue_item(run: HistoricalCapturedRun) -> OperatorDecisionQueueItem:
    return OperatorDecisionQueueItem(
        stage="evidence_problems",
        decision_label="Resolve evidence problem",
        evidence_line=f"{run.run_id} · captured_run_record_invalid",
        action_label="Inspect evidence →",
        action="inspect_evidence",
        run_id=run.run_id,
        task_file=None,
        adapter=run.summary.adapter if run.summary else None,
        run_status=run.summary.run_status if run.summary else None,
        verification_result=run.summary.verification_result if run.summary else None,
        acceptance_result=run.summary.acceptance_result if run.summary else None,
        changed_paths=run.summary.changed_paths if run.summary else [],
        failure_reason=run.summary.failure_reason if run.summary else None,
        evidence_error="captured_run_record_invalid",
    )


def _historical_verification_state(verification_status: object) -> str:
    if verification_status == "PASS":
        return "verified"
    if verification_status == "MISSING":
        return "unverified"
    return "failed"


def _evidence_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


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


def _approved_task_text(
    task_text: str,
    adapter: str,
    *,
    planning_session_id: str | None = None,
    planning_proposal_sha256: str | None = None,
) -> str:
    metadata = [f"<!-- axiom-forge-workbench-approved-adapter: {adapter} -->"]
    if planning_session_id is not None and planning_proposal_sha256 is not None:
        metadata.extend([
            f"<!-- axiom-forge-planning-session: {planning_session_id} -->",
            f"<!-- axiom-forge-planning-proposal-sha256: {planning_proposal_sha256} -->",
        ])
    return "\n".join([*metadata, task_text.rstrip(), ""])


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
    result = run_git(root, *args)
    if result.returncode != 0:
        raise WorkbenchApprovalError(failure_reason)
    return result.stdout.strip()


def _run_git(root: Path, args: list[str], failure_reason: str) -> None:
    _git_output(root, args, failure_reason)
