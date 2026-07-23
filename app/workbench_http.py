from __future__ import annotations

import json
import re
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from app.workbench_html import WORKBENCH_HTML
from app.workbench_models import (WorkbenchApprovalError, WorkbenchExecutionError, WorkbenchPromotionError, WorkbenchPromotionReviewError, WorkbenchVerificationError)
from app.planning_sessions import PlanningSessionError
from app.workbench_runtime import WorkbenchServer

def make_handler(workbench: WorkbenchServer) -> type[BaseHTTPRequestHandler]:
    class WorkbenchRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._write_html(WORKBENCH_HTML)
                return
            if parsed.path == "/api/planning-sessions":
                self._handle_planning_sessions()
                return
            if parsed.path.startswith("/api/planning-sessions/"):
                self._handle_planning_session_get(parsed.path)
                return
            if parsed.path == "/api/draft":
                self._handle_draft(parsed.query)
                return
            if parsed.path == "/api/decision-queue":
                self._handle_decision_queue()
                return
            if parsed.path.startswith("/api/promotion-reviews/"):
                self._handle_promotion_review_prepare(parsed.path)
                return
            if parsed.path == "/api/live-run":
                self._handle_live_run(parsed.query)
                return
            if parsed.path == "/api/runs":
                self._handle_history()
                return
            if parsed.path.startswith("/api/runs/"):
                self._handle_summary(parsed.path)
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/planning-sessions":
                self._handle_planning_session_start()
                return
            if parsed.path.startswith("/api/planning-sessions/"):
                self._handle_planning_session_post(parsed.path)
                return
            if parsed.path == "/api/approve":
                self._handle_approve()
                return
            if parsed.path == "/api/run":
                self._handle_run()
                return
            if parsed.path == "/api/retry":
                self._handle_retry()
                return
            if parsed.path == "/api/abandon":
                self._handle_abandon()
                return
            if parsed.path == "/api/promotion-reviews":
                self._handle_promotion_review_submit()
                return
            if parsed.path == "/api/promote":
                self._handle_promote()
                return
            if parsed.path == "/api/verify":
                self._handle_verify()
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def _handle_planning_sessions(self) -> None:
            try:
                sessions = workbench.planning_sessions_list()
            except PlanningSessionError as error:
                self._write_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
                return
            self._write_json({"authority": "planning_sessions", "sessions": sessions})

        def _handle_planning_session_get(self, path: str) -> None:
            match = re.fullmatch(r"/api/planning-sessions/([a-f0-9]{32})(?:/proposals/([1-9][0-9]*))?", path)
            if not match:
                self._write_json({"error": "invalid_planning_session_reference"}, HTTPStatus.BAD_REQUEST)
                return
            try:
                if match.group(2):
                    payload = workbench.planning_proposal_for_approval(match.group(1), int(match.group(2)))
                else:
                    payload = workbench.planning_session(match.group(1))
            except PlanningSessionError as error:
                self._write_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
                return
            self._write_json(payload)

        def _handle_planning_session_start(self) -> None:
            try:
                payload = self._read_planning_payload()
                session = workbench.start_planning_session(payload)
            except (UnicodeDecodeError, ValueError, PlanningSessionError) as error:
                self._write_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
                return
            self._write_json(session, HTTPStatus.CREATED)

        def _handle_planning_session_post(self, path: str) -> None:
            match = re.fullmatch(r"/api/planning-sessions/([a-f0-9]{32})/(messages|close)", path)
            if not match:
                self._write_json({"error": "invalid_planning_session_reference"}, HTTPStatus.BAD_REQUEST)
                return
            try:
                payload = self._read_planning_payload()
                if match.group(2) == "messages":
                    session = workbench.send_planning_message(match.group(1), payload)
                elif payload == {}:
                    session = workbench.close_planning_session(match.group(1))
                else:
                    raise PlanningSessionError("invalid_planning_close_request")
            except (UnicodeDecodeError, ValueError, PlanningSessionError) as error:
                self._write_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
                return
            self._write_json(session)

        def _read_planning_payload(self) -> object:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length < 1 or content_length > 1_000_000:
                raise PlanningSessionError("invalid_planning_session_request")
            return json.loads(self.rfile.read(content_length).decode("utf-8"))
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

        def _handle_abandon(self) -> None:
            try:
                payload = self._read_bounded_json("invalid_abandon_request")
                self._write_json(asdict(workbench.abandon_captured_run(payload)), HTTPStatus.CREATED)
            except (UnicodeDecodeError, ValueError, WorkbenchExecutionError) as error:
                self._write_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)

        def _handle_decision_queue(self) -> None:
            self._write_json(asdict(workbench.operator_decision_queue()))

        def _handle_promotion_review_prepare(self, path: str) -> None:
            match = re.fullmatch(r"/api/promotion-reviews/([0-9]{8}-[0-9]{6}-[0-9]+)", path)
            if not match:
                self._write_json({"error": "invalid_captured_run_reference"}, HTTPStatus.BAD_REQUEST)
                return
            try:
                self._write_json(asdict(workbench.prepare_promotion_review({"run_id": match.group(1)})))
            except (WorkbenchPromotionReviewError, WorkbenchVerificationError) as error:
                self._write_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)

        def _handle_promotion_review_submit(self) -> None:
            try:
                payload = self._read_bounded_json("invalid_promotion_review_submission")
                self._write_json(asdict(workbench.submit_promotion_review(payload)), HTTPStatus.CREATED)
            except (UnicodeDecodeError, ValueError, WorkbenchPromotionReviewError, WorkbenchVerificationError) as error:
                self._write_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)

        def _handle_promote(self) -> None:
            try:
                payload = self._read_bounded_json("invalid_promotion_confirmation")
                self._write_json(asdict(workbench.confirm_promotion(payload)), HTTPStatus.CREATED)
            except (UnicodeDecodeError, ValueError, WorkbenchPromotionError) as error:
                self._write_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)

        def _read_bounded_json(self, reason: str) -> object:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length < 1 or content_length > 1_000_000:
                raise ValueError(reason)
            return json.loads(self.rfile.read(content_length).decode("utf-8"))
        def _handle_live_run(self, query: str) -> None:
            if query:
                self._write_json({"error": "invalid_live_run_request"}, HTTPStatus.BAD_REQUEST)
                return
            self._write_json(workbench.live_run())

        def _handle_history(self) -> None:
            self._write_json(
                {
                    "authority": "historical_captured_runs",
                    "runs": [asdict(run) for run in workbench.historical_captured_runs()],
                }
            )

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
