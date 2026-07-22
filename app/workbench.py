from __future__ import annotations

# The stable application seam remains app.workbench.main for scripts/workbench.py.
from app.workbench_cli import main, run_server
from app.workbench_drafts import default_repo_from_origin, fetch_issue_with_gh, issue_to_draft_preview, parse_issue_reference
from app.workbench_html import WORKBENCH_HTML
from app.workbench_http import make_handler
from app.workbench_models import (
    DEFAULT_ADAPTERS, ApprovedDelegation, CapturedRun, ConfirmedExecution, ConfirmedRetry,
    DraftTaskPreview, HistoricalCapturedRun, IssueContext, IssueFetcher, IssueReference,
    OperatorEvidenceDetails, OperatorEvidenceSummary, PromotionResult, PromotionReviewPreparation,
    PromotionReviewSubmission, TargetRunner, VerificationRunner, WorkbenchApprovalError,
    WorkbenchExecutionError, WorkbenchPromotionError, WorkbenchPromotionReviewError,
    WorkbenchVerificationError,
)
from app.workbench_runtime import DraftApproval, WorkbenchServer


if __name__ == "__main__":
    raise SystemExit(main())
