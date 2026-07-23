from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

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
    comments: tuple[dict[str, str], ...] = ()


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
    planning_session_id: str | None = None
    planning_proposal_sha256: str | None = None


class WorkbenchApprovalError(ValueError):
    pass


class WorkbenchExecutionError(ValueError):
    pass


class WorkbenchVerificationError(ValueError):
    pass


class WorkbenchPromotionReviewError(ValueError):
    pass


class WorkbenchPromotionError(ValueError):
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
class HistoricalCapturedRun:
    authority: str
    run_id: str
    state: str
    verification_state: str
    read_only: bool
    summary: OperatorEvidenceSummary | None
    evidence_error: str | None

@dataclass(frozen=True)
class OperatorDecisionQueueItem:
    stage: str
    decision_label: str
    evidence_line: str
    action_label: str | None
    action: str | None
    run_id: str | None
    task_file: str | None
    adapter: str | None
    run_status: str | None
    verification_result: str | None
    acceptance_result: str | None
    changed_paths: list[str]
    failure_reason: str | None
    evidence_error: str | None
    planning_session_id: str | None = None
    planning_proposal_version: int | None = None
    target_repository: str | None = None
    target_branch: str | None = None
    target_base_sha: str | None = None
    reviewer: str | None = None
    review_decision: str | None = None
    review_concerns: str | None = None
    promotion_review_revision: str | None = None
    current_blocker: str | None = None


@dataclass(frozen=True)
class OperatorDecisionQueueStage:
    name: str
    label: str
    items: list[OperatorDecisionQueueItem]


@dataclass(frozen=True)
class OperatorDecisionQueue:
    authority: str
    stages: list[OperatorDecisionQueueStage]


@dataclass(frozen=True)
class OperatorEvidenceDetails:
    run_id: str
    stdout: str
    stderr: str
    patch_diff: str


@dataclass(frozen=True)
class PromotionReviewPreparation:
    authority: str
    run_id: str
    patch_sha256: str
    task_intent: str
    delegation_artifact_revision: str | None
    approved_scope: list[str]
    adapter: str
    target: dict[str, str | None]
    changed_paths: list[str]
    patch_diff: str
    verification: dict[str, str | None]
    acceptance_result: str
    evidence_problems: list[str]
    reviewer_hint: str | None


@dataclass(frozen=True)
class PromotionReviewSubmission:
    authority: str
    run_id: str
    decision: str
    promotion_review_revision: str


@dataclass(frozen=True)
class PromotionResult:
    authority: str
    run_id: str
    state: str
    reason: str | None
    branch: str | None
    promotion_commit: str | None
    promotion_review_revision: str | None
    promotion_record: dict[str, object] | None = None
    diagnostics: str = ""


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


@dataclass(frozen=True)
class AbandonedCapturedRun:
    authority: str
    run_id: str
    reason: str
    abandonment_revision: str


VerificationRunner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]
IssueFetcher = Callable[[IssueReference], IssueContext]
TargetRunner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]
