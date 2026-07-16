from __future__ import annotations

import json
import re
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from app.workbench_html import WORKBENCH_HTML
from app.workbench_models import WorkbenchApprovalError, WorkbenchExecutionError, WorkbenchVerificationError
from app.workbench_runtime import WorkbenchServer

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
            if parsed.path == "/api/runs":
                self._handle_history()
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
