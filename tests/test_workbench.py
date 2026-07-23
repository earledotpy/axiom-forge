import json
import subprocess
from dataclasses import asdict
import tempfile
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread
from urllib.request import Request, urlopen

from scripts.delegation_artifact_set import load_task_artifact_set

from app.workbench import (
    IssueContext,
    IssueReference,
    WorkbenchApprovalError,
    WorkbenchExecutionError,
    WorkbenchPromotionReviewError,
    WorkbenchVerificationError,
    WorkbenchServer,
    issue_to_draft_preview,
    make_handler,
    parse_issue_reference,
)


FIXTURE_ISSUE = IssueContext(
    number=49,
    title="Local workbench issue-to-draft preview",
    body=(
        "Build the first demoable local operator workbench path.\n\n"
        "The draft should mention `app/workbench.py` and `tests/test_workbench.py`."
    ),
    url="https://github.com/earledotpy/axiom-forge/issues/49",
    repo="earledotpy/axiom-forge",
)


class TestWorkbench(unittest.TestCase):
    def make_workbench(self, target_runner=None, verification_runner=None) -> tuple[WorkbenchServer, Path]:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "Axiom Test"], check=True)
        (root / "README.md").write_text("fixture\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "fixture"], check=True)
        return WorkbenchServer(
            lambda reference: FIXTURE_ISSUE,
            forge_root=root,
            target_runner=target_runner,
            verification_runner=verification_runner,
        ), root

    def approval_payload(self, **overrides):
        payload = {
            "issue_number": 49,
            "task_text": "Implement the approved workbench task.\n",
            "target_scope": "app/workbench.py\ntests/test_workbench.py\n",
            "acceptance_check": "#!/usr/bin/env bash\nset -Eeuo pipefail\necho checked\n",
            "adapter": "codex",
            "approved": True,
        }
        payload.update(overrides)
        return payload

    def execute_payload(self, **overrides):
        payload = {
            'task_file': 'tasks/workbench-issue-49.task.md',
            'confirmed': True,
        }
        payload.update(overrides)
        return payload

    def retry_payload(self, **overrides):
        payload = {
            'run_id': '20260712-010203-123456',
            'adapter': 'claude-code',
            'confirmed': True,
        }
        payload.update(overrides)
        return payload

    def approve_delegation(self, workbench: WorkbenchServer):
        workbench.approve_draft(self.approval_payload())

    @staticmethod
    def write_run_record(root: Path, run_id: str, status: str = 'COMPLETED') -> None:
        run_dir = root / 'runs' / run_id
        run_dir.mkdir(parents=True)
        record = {'run_id': run_id, 'run_status': status}
        if status == 'FAILED':
            record['failure_reason'] = 'adapter_unavailable'
        (run_dir / 'record.json').write_text(json.dumps(record), encoding='utf-8')

    @staticmethod
    def write_target_run_evidence(root: Path, run_id: str, record: dict | None = None) -> Path:
        run_dir = root / 'runs' / run_id
        run_dir.mkdir(parents=True)
        record = record or {'run_id': run_id, 'run_status': 'COMPLETED', 'failure_reason': None, 'agent': 'codex', 'run_mode': 'target'}
        if 'delegation_task_file' in record and 'delegation_artifact_revision' not in record:
            record = {
                **record,
                'delegation_artifact_revision': subprocess.check_output(
                    ['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True
                ).strip(),
            }
        run_dir.joinpath('record.json').write_text(
            json.dumps(record),
            encoding='utf-8',
        )
        run_dir.joinpath('task.md').write_text('Implement the target widget.\n', encoding='utf-8')
        run_dir.joinpath('allowed-paths.txt').write_text('app/widget.py\n', encoding='utf-8')
        run_dir.joinpath('patch.diff').write_text(
            'diff --git a/app/widget.py b/app/widget.py\n'
            'index 1111111..2222222 100644\n'
            '--- a/app/widget.py\n'
            '+++ b/app/widget.py\n',
            encoding='utf-8',
        )
        run_dir.joinpath('stdout.log').write_text('adapter stdout\n', encoding='utf-8')
        run_dir.joinpath('stderr.log').write_text('adapter stderr\n', encoding='utf-8')
        return run_dir

    def test_parse_issue_reference_accepts_number_hash_and_url(self):
        self.assertEqual(parse_issue_reference("49", "owner/repo"), IssueReference(49, "owner/repo"))
        self.assertEqual(parse_issue_reference("#49", "owner/repo"), IssueReference(49, "owner/repo"))
        self.assertEqual(
            parse_issue_reference("https://github.com/earledotpy/axiom-forge/issues/49"),
            IssueReference(49, "earledotpy/axiom-forge"),
        )

    def test_issue_to_draft_preview_prefers_what_to_build_context(self):
        issue = IssueContext(
            number=49,
            title="Local workbench issue-to-draft preview",
            body=(
                "## Parent\n\nParent PRD: #48\n\n"
                "## What to build\n\nBuild the browser UI from the planning source.\n\n"
                "## Acceptance criteria\n\n- [ ] It works"
            ),
            url="https://github.com/earledotpy/axiom-forge/issues/49",
            repo="earledotpy/axiom-forge",
        )

        preview = issue_to_draft_preview(issue, adapter_options=["codex"])

        self.assertIn("Build the browser UI from the planning source.", preview.task_intent)
        self.assertNotIn("Parent PRD", preview.task_intent)

    def test_issue_to_draft_preview_contains_editable_draft_fields(self):
        preview = issue_to_draft_preview(FIXTURE_ISSUE, adapter_options=["codex", "claude-code"])

        self.assertEqual(preview.authority, "draft_only")
        self.assertIn("Local workbench issue-to-draft preview", preview.task_intent)
        self.assertIn("Planning source: https://github.com/earledotpy/axiom-forge/issues/49", preview.task_text)
        self.assertEqual(preview.target_scope, "app/workbench.py\ntests/test_workbench.py")
        self.assertIn("Issue #49", preview.acceptance_check)
        self.assertEqual(preview.draft_adapter, "codex")
        self.assertEqual(preview.adapter_options, ["codex", "claude-code"])

    def test_http_draft_endpoint_uses_fixture_fetcher_without_persistence(self):
        requested_references = []

        def fetch_issue(reference):
            requested_references.append(reference)
            return FIXTURE_ISSUE

        server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            make_handler(WorkbenchServer(fetch_issue, default_repo="earledotpy/axiom-forge")),
        )
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(f"http://127.0.0.1:{server.server_port}/api/draft?issue=49") as response:
                payload = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(requested_references, [IssueReference(49, "earledotpy/axiom-forge")])
        self.assertEqual(payload["authority"], "draft_only")
        self.assertEqual(payload["source_issue"]["number"], 49)
        self.assertIn("task_text", payload)
        self.assertIn("target_scope", payload)
        self.assertIn("acceptance_check", payload)
        self.assertIn("draft_adapter", payload)

    def test_approval_creates_committed_delegation_artifacts(self):
        workbench, root = self.make_workbench()

        delegation = workbench.approve_draft(self.approval_payload())

        self.assertEqual(delegation.authority, "approved_delegation")
        self.assertEqual(delegation.adapter, "codex")
        self.assertEqual(delegation.task_file, "tasks/workbench-issue-49.task.md")
        self.assertEqual(delegation.scope_file, "tasks/workbench-issue-49.allowed-paths.txt")
        self.assertEqual(delegation.acceptance_file, "tasks/workbench-issue-49.accept.sh")
        self.assertEqual(
            load_task_artifact_set(root / delegation.task_file).approved_adapter,
            "codex",
        )
        self.assertEqual(
            (root / delegation.task_file).read_text(encoding="utf-8"),
            "<!-- axiom-forge-workbench-approved-adapter: codex -->\nImplement the approved workbench task.\n",
        )
        self.assertEqual(
            (root / delegation.scope_file).read_text(encoding="utf-8"),
            "app/workbench.py\ntests/test_workbench.py\n",
        )
        self.assertEqual(
            (root / delegation.acceptance_file).read_text(encoding="utf-8"),
            "#!/usr/bin/env bash\nset -Eeuo pipefail\necho checked\n",
        )
        self.assertEqual(
            subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"], text=True),
            "",
        )
        self.assertEqual(
            delegation.delegation_artifact_revision,
            subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip(),
        )

    def test_approval_requires_explicit_confirmation_before_writing_artifacts(self):
        workbench, root = self.make_workbench()

        with self.assertRaises(WorkbenchApprovalError) as caught:
            workbench.approve_draft(self.approval_payload(approved=False))

        self.assertEqual(str(caught.exception), "operator_approval_required")
        self.assertFalse((root / "tasks").exists())

    def test_approval_rejects_invalid_task_text_without_writing_artifacts(self):
        workbench, root = self.make_workbench()

        with self.assertRaises(WorkbenchApprovalError) as caught:
            workbench.approve_draft(self.approval_payload(task_text="unsafe\x00task"))

        self.assertEqual(str(caught.exception), "invalid_approved_task_text")
        self.assertFalse((root / "tasks").exists())

    def test_approval_rejects_invalid_target_scope_without_writing_artifacts(self):
        workbench, root = self.make_workbench()

        with self.assertRaises(WorkbenchApprovalError) as caught:
            workbench.approve_draft(self.approval_payload(target_scope="../outside.py\n"))

        self.assertEqual(str(caught.exception), "invalid_target_task_scope")
        self.assertFalse((root / "tasks").exists())

    def test_approval_rejects_acceptance_check_inside_target_scope_without_writing_artifacts(self):
        workbench, root = self.make_workbench()

        with self.assertRaises(WorkbenchApprovalError) as caught:
            workbench.approve_draft(
                self.approval_payload(target_scope="tasks/workbench-issue-49.accept.sh\n")
            )

        self.assertEqual(str(caught.exception), "target_acceptance_check_in_scope")
        self.assertFalse((root / "tasks").exists())

    def test_http_approval_endpoint_returns_committed_authority(self):
        workbench, root = self.make_workbench()
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(workbench))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = Request(
                f"http://127.0.0.1:{server.server_port}/api/approve",
                data=json.dumps(self.approval_payload()).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request) as response:
                payload = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(payload["authority"], "approved_delegation")
        self.assertEqual(payload["adapter"], "codex")
        self.assertTrue((root / payload["task_file"]).exists())

    def test_confirmed_execution_runs_only_the_approved_target_mode_task(self):
        calls = []
        run_id = "20260712-010203-123456"

        def target_runner(command, root):
            calls.append((command, root))
            self.write_run_record(root, run_id)
            return subprocess.CompletedProcess(command, 0, f"RUN_CAPTURED: {run_id}\n", "")

        workbench, root = self.make_workbench(target_runner=target_runner)
        self.approve_delegation(workbench)

        captured_run = workbench.execute_confirmed_delegation(self.execute_payload())

        self.assertEqual(captured_run.run_id, run_id)
        self.assertEqual(captured_run.run_status, "COMPLETED")
        self.assertIsNone(captured_run.failure_reason)
        self.assertEqual(
            calls,
            [
                (
                    [
                        "bash",
                        str(root / "scripts" / "run_agent_task.sh"),
                        "--target",
                        "codex",
                        "tasks/workbench-issue-49.task.md",
                    ],
                    root,
                )
            ],
        )

    def test_execution_requires_confirmation_without_starting_a_runner(self):
        calls = []
        workbench, _ = self.make_workbench(target_runner=lambda command, root: calls.append(command))
        self.approve_delegation(workbench)

        with self.assertRaises(WorkbenchExecutionError) as caught:
            workbench.execute_confirmed_delegation(self.execute_payload(confirmed=False))

        self.assertEqual(str(caught.exception), "operator_execution_confirmation_required")
        self.assertEqual(calls, [])

    def test_execution_surfaces_a_bounded_scrubbed_runner_diagnostic_without_a_capture_sentinel(self):
        def target_runner(command, root):
            return subprocess.CompletedProcess(
                command,
                127,
                "early stdout\n",
                "x" * 4096 + "\nOPENAI_API_KEY=sk-openai-secret\nAuthorization: Basic basic-secret\nAuthorization=Bearer equals-secret\n{\"Authorization\": \"Bearer bearer-secret\"}\n{\"access_token\": \"json-secret\"}\npassword: \"secret with spaces\"\n",
            )

        workbench, _ = self.make_workbench(target_runner=target_runner)
        self.approve_delegation(workbench)

        with self.assertRaises(WorkbenchExecutionError) as caught:
            workbench.execute_confirmed_delegation(self.execute_payload())

        message = str(caught.exception)
        self.assertTrue(message.startswith("target_mode_runner_did_not_capture_run: "))
        for secret in ("sk-openai-secret", "basic-secret", "equals-secret", "bearer-secret", "json-secret", "secret with spaces"):
            self.assertNotIn(secret, message)
        self.assertIn("[REDACTED]", message)
        self.assertLessEqual(len(message), 2048)


    def test_execution_rejects_generic_command_requests_without_starting_a_runner(self):
        calls = []
        workbench, _ = self.make_workbench(target_runner=lambda command, root: calls.append(command))
        self.approve_delegation(workbench)

        with self.assertRaises(WorkbenchExecutionError) as caught:
            workbench.execute_confirmed_delegation(
                self.execute_payload(command=["bash", "arbitrary-command.sh"])
            )

        self.assertEqual(str(caught.exception), "generic_command_execution_forbidden")
        self.assertEqual(calls, [])

    def test_execution_rejects_a_second_active_delegation(self):
        started = Event()
        release = Event()
        run_id = "20260712-010203-123456"

        def target_runner(command, root):
            started.set()
            self.assertTrue(release.wait(timeout=5))
            self.write_run_record(root, run_id)
            return subprocess.CompletedProcess(command, 0, f"RUN_CAPTURED: {run_id}\n", "")

        workbench, _ = self.make_workbench(target_runner=target_runner)
        self.approve_delegation(workbench)
        first_result = []
        first = Thread(
            target=lambda: first_result.append(
                workbench.execute_confirmed_delegation(self.execute_payload())
            )
        )
        first.start()
        self.assertTrue(started.wait(timeout=5))
        try:
            with self.assertRaises(WorkbenchExecutionError) as caught:
                workbench.execute_confirmed_delegation(self.execute_payload())
            self.assertEqual(str(caught.exception), "active_workbench_delegation_in_progress")
        finally:
            release.set()
            first.join(timeout=5)

        self.assertFalse(first.is_alive())
        self.assertEqual(first_result[0].run_id, run_id)

    def test_retry_requires_confirmation_and_does_not_start_automatically(self):
        calls = []
        workbench, root = self.make_workbench(target_runner=lambda command, root: calls.append(command))
        self.approve_delegation(workbench)
        self.write_target_run_evidence(
            root,
            '20260712-010203-123456',
            {
                'run_id': '20260712-010203-123456',
                'run_status': 'FAILED',
                'failure_reason': 'adapter_unavailable',
                'agent': 'codex',
                'delegation_task_file': 'tasks/workbench-issue-49.task.md',
            },
        )

        with self.assertRaises(WorkbenchExecutionError) as caught:
            workbench.retry_confirmed_delegation(self.retry_payload(confirmed=False))

        self.assertEqual(str(caught.exception), 'operator_retry_confirmation_required')
        self.assertEqual(calls, [])

    def test_retry_uses_the_failed_run_approved_task_with_the_selected_adapter(self):
        calls = []
        retry_id = '20260712-010204-654321'

        def target_runner(command, root):
            calls.append((command, root))
            self.write_run_record(root, retry_id)
            return subprocess.CompletedProcess(command, 0, f'RUN_CAPTURED: {retry_id}\n', '')

        workbench, root = self.make_workbench(target_runner=target_runner)
        self.approve_delegation(workbench)
        self.write_target_run_evidence(
            root,
            '20260712-010203-123456',
            {
                'run_id': '20260712-010203-123456',
                'run_status': 'FAILED',
                'failure_reason': 'adapter_unavailable',
                'agent': 'codex',
                'delegation_task_file': 'tasks/workbench-issue-49.task.md',
            },
        )

        captured_run = workbench.retry_confirmed_delegation(self.retry_payload())

        self.assertEqual(captured_run.run_id, retry_id)
        self.assertEqual(
            calls,
            [
                (
                    [
                        'bash',
                        str(root / 'scripts' / 'run_agent_task.sh'),
                        '--target',
                        'claude-code',
                        'tasks/workbench-issue-49.task.md',
                    ],
                    root,
                )
            ],
        )

    def test_retry_rejects_a_run_without_failed_or_unusable_evidence(self):
        calls = []
        workbench, root = self.make_workbench(target_runner=lambda command, root: calls.append(command))
        self.approve_delegation(workbench)
        self.write_target_run_evidence(
            root,
            '20260712-010203-123456',
            {
                'run_id': '20260712-010203-123456',
                'run_status': 'COMPLETED',
                'failure_reason': None,
                'agent': 'codex',
                'delegation_task_file': 'tasks/workbench-issue-49.task.md',
            },
        )

        with self.assertRaises(WorkbenchExecutionError) as caught:
            workbench.retry_confirmed_delegation(self.retry_payload())

        self.assertEqual(str(caught.exception), 'captured_run_not_retryable')
        self.assertEqual(calls, [])

    def test_retry_rejects_changed_delegation_boundary(self):
        calls = []
        workbench, root = self.make_workbench(target_runner=lambda command, root: calls.append(command))
        self.approve_delegation(workbench)
        self.write_target_run_evidence(
            root,
            '20260712-010203-123456',
            {
                'run_id': '20260712-010203-123456',
                'run_status': 'FAILED',
                'failure_reason': 'adapter_unavailable',
                'agent': 'codex',
                'delegation_task_file': 'tasks/workbench-issue-49.task.md',
            },
        )
        (root / 'tasks' / 'workbench-issue-49.allowed-paths.txt').write_text(
            'app/other.py\n', encoding='utf-8'
        )

        with self.assertRaises(WorkbenchExecutionError) as caught:
            workbench.retry_confirmed_delegation(self.retry_payload())

        self.assertEqual(str(caught.exception), 'retry_delegation_boundary_changed')
        self.assertEqual(calls, [])
    def test_retry_accepts_unusable_verification_evidence(self):
        retry_id = '20260712-010204-654321'

        def target_runner(command, root):
            self.write_run_record(root, retry_id)
            return subprocess.CompletedProcess(command, 0, f'RUN_CAPTURED: {retry_id}\n', '')

        workbench, root = self.make_workbench(target_runner=target_runner)
        self.approve_delegation(workbench)
        failed_verification = self.write_target_run_evidence(
            root,
            '20260712-010203-123456',
            {
                'run_id': '20260712-010203-123456',
                'run_status': 'COMPLETED',
                'failure_reason': None,
                'agent': 'codex',
                'delegation_task_file': 'tasks/workbench-issue-49.task.md',
            },
        )
        failed_verification.joinpath('verify.json').write_text(
            json.dumps({'status': 'FAIL', 'reason': 'target_acceptance_failed'}), encoding='utf-8'
        )

        captured_run = workbench.retry_confirmed_delegation(self.retry_payload())

        self.assertEqual(captured_run.run_id, retry_id)

    def test_retry_is_blocked_while_another_delegation_is_active(self):
        started = Event()
        release = Event()
        run_id = '20260712-010203-123456'

        def target_runner(command, root):
            started.set()
            self.assertTrue(release.wait(timeout=5))
            self.write_run_record(root, run_id)
            return subprocess.CompletedProcess(command, 0, f'RUN_CAPTURED: {run_id}\n', '')

        workbench, root = self.make_workbench(target_runner=target_runner)
        self.approve_delegation(workbench)
        self.write_target_run_evidence(
            root,
            '20260712-010203-123457',
            {
                'run_id': '20260712-010203-123457',
                'run_status': 'FAILED',
                'failure_reason': 'adapter_unavailable',
                'agent': 'codex',
                'delegation_task_file': 'tasks/workbench-issue-49.task.md',
            },
        )
        active = Thread(target=lambda: workbench.execute_confirmed_delegation(self.execute_payload()))
        active.start()
        self.assertTrue(started.wait(timeout=5))
        try:
            with self.assertRaises(WorkbenchExecutionError) as caught:
                workbench.retry_confirmed_delegation(
                    self.retry_payload(run_id='20260712-010203-123457')
                )
            self.assertEqual(str(caught.exception), 'active_workbench_delegation_in_progress')
        finally:
            release.set()
            active.join(timeout=5)

        self.assertFalse(active.is_alive())

    def test_http_retry_requires_confirmation_and_uses_the_selected_adapter(self):
        retry_id = '20260712-010204-654321'
        calls = []

        def target_runner(command, root):
            calls.append(command)
            self.write_run_record(root, retry_id)
            return subprocess.CompletedProcess(command, 0, f'RUN_CAPTURED: {retry_id}\n', '')

        workbench, root = self.make_workbench(target_runner=target_runner)
        self.approve_delegation(workbench)
        self.write_target_run_evidence(
            root,
            '20260712-010203-123456',
            {
                'run_id': '20260712-010203-123456',
                'run_status': 'FAILED',
                'failure_reason': 'adapter_unavailable',
                'agent': 'codex',
                'delegation_task_file': 'tasks/workbench-issue-49.task.md',
            },
        )
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(workbench))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = Request(
                f'http://127.0.0.1:{server.server_port}/api/retry',
                data=json.dumps(self.retry_payload()).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                method='POST',
            )
            with urlopen(request) as response:
                payload = json.loads(response.read().decode('utf-8'))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(payload['run_id'], retry_id)
        self.assertEqual(calls[0][-2:], ['claude-code', 'tasks/workbench-issue-49.task.md'])

    def test_http_execution_endpoint_returns_captured_run_identity_and_status(self):
        run_id = "20260712-010203-123456"

        def target_runner(command, root):
            self.write_run_record(root, run_id, status="FAILED")
            return subprocess.CompletedProcess(command, 1, f"RUN_FAILED: {run_id}\n", "")

        workbench, _ = self.make_workbench(target_runner=target_runner)
        self.approve_delegation(workbench)
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(workbench))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = Request(
                f"http://127.0.0.1:{server.server_port}/api/run",
                data=json.dumps(self.execute_payload()).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request) as response:
                payload = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(payload["run_id"], run_id)
        self.assertEqual(payload["run_status"], "FAILED")
        self.assertEqual(payload["failure_reason"], "adapter_unavailable")

    def test_target_verification_returns_evidence_first_summary_for_a_passing_run(self):
        run_id = '20260712-010203-123456'

        def verification_runner(command, root):
            self.assertEqual(command, ['bash', str(root / 'scripts' / 'verify_patch.sh'), '--target', f'runs/{run_id}'])
            (root / 'runs' / run_id / 'verify.json').write_text(
                json.dumps({'status': 'PASS', 'acceptance': {'returncode': 0}}), encoding='utf-8'
            )
            return subprocess.CompletedProcess(command, 0, f'VERIFY_PATCH: PASS {run_id}\n', '')

        workbench, root = self.make_workbench(verification_runner=verification_runner)
        self.write_target_run_evidence(root, run_id)

        summary = workbench.verify_captured_run({'run_id': run_id})

        self.assertEqual(summary.run_id, run_id)
        self.assertEqual(summary.task_intent, 'Implement the target widget.')
        self.assertEqual(summary.approved_scope, ['app/widget.py'])
        self.assertEqual(summary.adapter, 'codex')
        self.assertEqual(summary.run_status, 'COMPLETED')
        self.assertEqual(summary.changed_paths, ['app/widget.py'])
        self.assertEqual(summary.verification_result, 'PASS')
        self.assertEqual(summary.acceptance_result, 'PASS')
        self.assertIsNone(summary.failure_reason)
        self.assertEqual(summary.next_allowed_actions, ['inspect_details', 'prepare_review'])

    def test_summary_prefers_the_approved_task_intent_section(self):
        run_id = '20260712-010203-123456'
        workbench, root = self.make_workbench()
        run_dir = self.write_target_run_evidence(root, run_id)
        run_dir.joinpath('task.md').write_text(
            'Implement Issue #52.\n\nTask intent:\nShow verified evidence to the operator.\n\nConstraints:\n- No promotion.\n',
            encoding='utf-8',
        )

        summary = workbench.summary_for_captured_run(run_id)

        self.assertEqual(summary.task_intent, 'Show verified evidence to the operator.')
    def test_target_verification_summarizes_a_failed_verification(self):
        run_id = '20260712-010203-123456'

        def verification_runner(command, root):
            (root / 'runs' / run_id / 'verify.json').write_text(
                json.dumps({'status': 'FAIL', 'reason': 'target_acceptance_failed', 'acceptance': {'returncode': 1}}), encoding='utf-8'
            )
            return subprocess.CompletedProcess(command, 1, '', 'ERROR: verification_failed\n')

        workbench, root = self.make_workbench(verification_runner=verification_runner)
        self.write_target_run_evidence(root, run_id)

        summary = workbench.verify_captured_run({'run_id': run_id})

        self.assertEqual(summary.verification_result, 'FAIL')
        self.assertEqual(summary.verification_reason, 'target_acceptance_failed')
        self.assertEqual(summary.acceptance_result, 'FAIL')
        self.assertEqual(summary.next_allowed_actions, ['inspect_details', 'retry_later'])

    def test_failed_run_record_remains_visible_without_running_verification(self):
        run_id = '20260712-010203-123456'
        calls = []
        workbench, root = self.make_workbench(verification_runner=lambda command, root: calls.append(command))
        self.write_target_run_evidence(
            root,
            run_id,
            {'run_id': run_id, 'run_status': 'FAILED', 'failure_reason': 'adapter_unavailable', 'agent': 'codex', 'run_mode': 'target'},
        )

        summary = workbench.summary_for_captured_run(run_id)

        self.assertEqual(summary.run_status, 'FAILED')
        self.assertEqual(summary.failure_reason, 'adapter_unavailable')
        self.assertEqual(summary.verification_result, 'NOT_RUN')
        self.assertEqual(summary.next_allowed_actions, ['inspect_details', 'retry_later'])
        self.assertEqual(calls, [])

    def test_summary_handles_missing_evidence_fields_without_hiding_the_run(self):
        run_id = '20260712-010203-123456'
        workbench, root = self.make_workbench()
        run_dir = root / 'runs' / run_id
        run_dir.mkdir(parents=True)
        run_dir.joinpath('record.json').write_text(json.dumps({'run_id': run_id, 'run_status': 'COMPLETED'}), encoding='utf-8')

        summary = workbench.summary_for_captured_run(run_id)

        self.assertEqual(summary.task_intent, 'missing_task_intent')
        self.assertEqual(summary.approved_scope, [])
        self.assertEqual(summary.adapter, 'missing_adapter')
        self.assertEqual(summary.changed_paths, [])
        self.assertEqual(summary.verification_result, 'NOT_RUN')
        self.assertEqual(summary.acceptance_result, 'NOT_RUN')

    def test_verification_rejects_an_invalid_run_request_without_starting_a_runner(self):
        calls = []
        workbench, _ = self.make_workbench(verification_runner=lambda command, root: calls.append(command))

        with self.assertRaises(WorkbenchVerificationError) as caught:
            workbench.verify_captured_run({'run_id': '../not-a-run'})

        self.assertEqual(str(caught.exception), 'invalid_captured_run_reference')
        self.assertEqual(calls, [])

    def test_workbench_html_renders_the_required_summary_fields_and_drill_down(self):
        from app.workbench import WORKBENCH_HTML

        for field in (
            'Task intent',
            'Approved scope',
            'Adapter',
            'Run status',
            'Changed paths',
            'Verification',
            'Acceptance',
            'Failure reason',
            'Next allowed actions',
            'Raw stdout, stderr, and patch diff',
        ):
            self.assertIn(field, WORKBENCH_HTML)
        self.assertIn('renderEvidenceSummary', WORKBENCH_HTML)
        self.assertIn('/api/runs/${runId}/details', WORKBENCH_HTML)

    def test_workbench_html_presents_confirmed_operator_directed_retry(self):
        from app.workbench import WORKBENCH_HTML

        self.assertIn('Retry Approved Task', WORKBENCH_HTML)
        self.assertIn('I confirm that I want to retry this approved task now.', WORKBENCH_HTML)
        self.assertIn('fetch("/api/retry"', WORKBENCH_HTML)
        self.assertIn('adapter: retryAdapter.value', WORKBENCH_HTML)
        self.assertIn('confirmed: retryConfirmation.checked', WORKBENCH_HTML)
        self.assertIn('Prior failed evidence summary', WORKBENCH_HTML)
        self.assertIn('evidenceSummary.cloneNode(true)', WORKBENCH_HTML)

    def test_http_summary_keeps_raw_evidence_in_the_drill_down_endpoint(self):
        run_id = '20260712-010203-123456'
        workbench, root = self.make_workbench()
        self.write_target_run_evidence(root, run_id)
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(workbench))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(f"http://127.0.0.1:{server.server_port}/api/runs/{run_id}") as response:
                summary = json.loads(response.read().decode("utf-8"))
            with urlopen(f"http://127.0.0.1:{server.server_port}/api/runs/{run_id}/details") as response:
                details = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(summary['authority'], 'operator_evidence_summary')
        self.assertEqual(summary['changed_paths'], ['app/widget.py'])
        self.assertNotIn('stdout', summary)
        self.assertEqual(details['stdout'], 'adapter stdout\n')
        self.assertEqual(details['stderr'], 'adapter stderr\n')
        self.assertIn('diff --git', details['patch_diff'])

    def test_historical_runs_are_discovered_read_only_from_existing_evidence(self):
        completed_id = '20260712-010203-000001'
        verified_id = '20260712-010203-000002'
        failed_id = '20260712-010203-000003'
        superseded_id = '20260712-010203-000004'
        workbench, root = self.make_workbench()
        self.write_target_run_evidence(root, completed_id)
        verified_run = self.write_target_run_evidence(root, verified_id)
        verified_run.joinpath('verify.json').write_text(
            json.dumps({'status': 'PASS', 'acceptance': {'returncode': 0}}), encoding='utf-8'
        )
        self.write_target_run_evidence(
            root,
            failed_id,
            {'run_id': failed_id, 'run_status': 'FAILED', 'failure_reason': 'adapter_unavailable'},
        )
        self.write_target_run_evidence(
            root,
            superseded_id,
            {
                'run_id': superseded_id,
                'run_status': 'COMPLETED',
                'superseded_by_run_id': '20260712-020304-000005',
                'superseded_reason': 'newer_delegation_target_base',
            },
        )

        history = workbench.historical_captured_runs()
        by_run_id = {entry.run_id: entry for entry in history}

        self.assertEqual(set(by_run_id), {completed_id, verified_id, failed_id, superseded_id})
        self.assertTrue(all(entry.read_only for entry in history))
        self.assertEqual(by_run_id[completed_id].state, 'captured')
        self.assertEqual(by_run_id[completed_id].summary.run_status, 'COMPLETED')
        self.assertEqual(by_run_id[completed_id].verification_state, 'unverified')
        self.assertEqual(by_run_id[verified_id].state, 'verified')
        self.assertEqual(by_run_id[verified_id].verification_state, 'verified')
        self.assertEqual(by_run_id[failed_id].state, 'failed')
        self.assertEqual(by_run_id[failed_id].verification_state, 'unverified')
        self.assertEqual(by_run_id[superseded_id].state, 'superseded')
        self.assertEqual(by_run_id[superseded_id].verification_state, 'unverified')

    def test_historical_run_surfaces_adapter_availability_failure_state(self):
        run_id = '20260712-010203-000006'
        workbench, root = self.make_workbench()
        self.write_target_run_evidence(
            root,
            run_id,
            {
                'run_id': run_id,
                'run_status': 'FAILED',
                'failure_reason': 'adapter_quota_exhausted',
                'failure_class': 'adapter_availability',
                'agent': 'codex',
                'run_mode': 'target',
            },
        )

        history = workbench.historical_captured_runs()

        self.assertEqual(history[0].state, 'availability-failure')
        self.assertEqual(history[0].summary.failure_reason, 'adapter_quota_exhausted')
        self.assertEqual(history[0].summary.next_allowed_actions, ['inspect_details', 'retry_later'])

    def test_historical_run_surfaces_promotion_ready_state(self):
        run_id = '20260712-010203-000007'
        workbench, root = self.make_workbench()
        run_dir = self.write_target_run_evidence(
            root,
            run_id,
            {
                'run_id': run_id,
                'run_status': 'COMPLETED',
                'failure_reason': None,
                'agent': 'codex',
                'run_mode': 'target',
                'patch_sha256': 'b' * 64,
            },
        )
        run_dir.joinpath('verify.json').write_text(
            json.dumps({'status': 'PASS', 'acceptance': {'returncode': 0}}), encoding='utf-8'
        )
        review_path = root / 'reviews' / 'promotion' / f'{run_id}.json'
        review_path.parent.mkdir(parents=True)
        review_path.write_text(
            json.dumps(
                {
                    'schema_version': 1,
                    'review_type': 'promotion',
                    'run_id': run_id,
                    'patch_sha256': 'b' * 64,
                    'reviewer': 'operator',
                    'decision': 'APPROVED',
                    'concerns': 'No concerns.',
                    'follow_up_tasks': [],
                    'evidence_attestation': True,
                }
            ),
            encoding='utf-8',
        )
        subprocess.run(['git', '-C', str(root), 'add', 'reviews/promotion'], check=True)
        subprocess.run(['git', '-C', str(root), 'commit', '-q', '-m', 'Record promotion review'], check=True)

        history = workbench.historical_captured_runs()

        self.assertEqual(history[0].state, 'promotion-ready')
        self.assertEqual(history[0].verification_state, 'verified')
        self.assertEqual(history[0].summary.acceptance_result, 'PASS')

    def test_http_history_lists_read_only_runs_and_missing_evidence(self):
        completed_id = '20260712-010203-000001'
        missing_id = '20260712-010203-000002'
        workbench, root = self.make_workbench()
        self.write_target_run_evidence(root, completed_id)
        (root / 'runs' / missing_id).mkdir(parents=True)
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(workbench))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(f"http://127.0.0.1:{server.server_port}/api/runs") as response:
                payload = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        by_run_id = {entry['run_id']: entry for entry in payload['runs']}
        self.assertEqual(payload['authority'], 'historical_captured_runs')
        self.assertTrue(by_run_id[completed_id]['read_only'])
        self.assertEqual(by_run_id[completed_id]['state'], 'captured')
        self.assertEqual(by_run_id[completed_id]['verification_state'], 'unverified')
        self.assertEqual(by_run_id[completed_id]['summary']['run_status'], 'COMPLETED')
        self.assertEqual(by_run_id[missing_id]['state'], 'missing_evidence')
        self.assertIsNone(by_run_id[missing_id]['summary'])
        self.assertEqual(by_run_id[missing_id]['verification_state'], 'missing_evidence')
        self.assertEqual(by_run_id[missing_id]['evidence_error'], 'captured_run_record_unavailable')

    def test_http_live_run_reads_bounded_labelled_tails_without_mutation(self):
        run_id = '20260712-010203-000009'
        workbench, root = self.make_workbench()
        run_dir = root / 'runs' / run_id
        run_dir.mkdir(parents=True)
        run_dir.joinpath('stdout.log').write_text('a' * (64 * 1024 + 1), encoding='utf-8')
        run_dir.joinpath('stderr.log').write_bytes(b'stderr tail\n')
        live_state = root / 'runs' / '.live-run.json'
        live_state.write_text(
            json.dumps(
                {
                    'schema_version': 1,
                    'run_id': run_id,
                    'lifecycle_state': 'active',
                    'stdout_log': f'runs/{run_id}/stdout.log',
                    'stderr_log': f'runs/{run_id}/stderr.log',
                }
            ),
            encoding='utf-8',
        )
        before = live_state.read_bytes(), run_dir.joinpath('stdout.log').read_bytes(), run_dir.joinpath('stderr.log').read_bytes()
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(workbench))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(f'http://127.0.0.1:{server.server_port}/api/live-run') as response:
                payload = json.loads(response.read().decode('utf-8'))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(payload['state'], 'active')
        self.assertEqual(payload['run_id'], run_id)
        self.assertTrue(payload['stdout']['truncated'])
        self.assertEqual(len(payload['stdout']['text']), 64 * 1024)
        self.assertEqual(payload['stderr'], {'text': 'stderr tail\n', 'truncated': False})
        self.assertEqual(
            before,
            (live_state.read_bytes(), run_dir.joinpath('stdout.log').read_bytes(), run_dir.joinpath('stderr.log').read_bytes()),
        )

    def test_http_live_run_returns_terminal_and_fails_closed_for_invalid_state(self):
        run_id = '20260712-010203-000010'
        workbench, root = self.make_workbench()
        live_state = root / 'runs' / '.live-run.json'
        live_state.parent.mkdir()
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(workbench))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            live_state.write_text('{not-json', encoding='utf-8')
            with urlopen(f'http://127.0.0.1:{server.server_port}/api/live-run') as response:
                invalid_payload = json.loads(response.read().decode('utf-8'))

            live_state.write_text(
                json.dumps(
                    {
                        'schema_version': 1,
                        'run_id': run_id,
                        'lifecycle_state': 'active',
                        'stdout_log': 'outside/stdout.log',
                        'stderr_log': f'runs/{run_id}/stderr.log',
                    }
                ),
                encoding='utf-8',
            )
            with urlopen(f'http://127.0.0.1:{server.server_port}/api/live-run') as response:
                out_of_root_payload = json.loads(response.read().decode('utf-8'))
            live_state.write_text(
                json.dumps(
                    {
                        'schema_version': 1,
                        'run_id': run_id,
                        'lifecycle_state': 'terminal',
                        'stdout_log': f'runs/{run_id}/stdout.log',
                        'stderr_log': f'runs/{run_id}/stderr.log',
                    }
                ),
                encoding='utf-8',
            )
            with urlopen(f'http://127.0.0.1:{server.server_port}/api/live-run') as response:
                terminal_payload = json.loads(response.read().decode('utf-8'))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(
            invalid_payload,
            {'authority': 'live_run_stream', 'state': 'unavailable', 'reason': 'live_run_state_invalid'},
        )
        self.assertEqual(
            out_of_root_payload,
            {'authority': 'live_run_stream', 'state': 'unavailable', 'reason': 'live_run_state_invalid'},
        )
        self.assertEqual(
            terminal_payload,
            {'authority': 'live_run_stream', 'state': 'terminal', 'run_id': run_id},
        )

    def test_workbench_html_includes_a_read_only_historical_run_view(self):
        from app.workbench import WORKBENCH_HTML

        self.assertIn('Historical captured runs', WORKBENCH_HTML)
        self.assertIn('View evidence summary', WORKBENCH_HTML)
        self.assertIn('fetch("/api/runs")', WORKBENCH_HTML)
        self.assertIn('if (!readOnly && payload.verification_result === "NOT_RUN"', WORKBENCH_HTML)
        self.assertIn('if (!readOnly && (payload.run_status === "FAILED"', WORKBENCH_HTML)
        self.assertIn('renderEvidenceSummary(entry.run_id, false, true)', WORKBENCH_HTML)
        self.assertLess(WORKBENCH_HTML.index('</aside>'), WORKBENCH_HTML.index('id="evidence-summary"'))
        self.assertLess(WORKBENCH_HTML.index('id="evidence-summary"'), WORKBENCH_HTML.index('</section>'))

    def test_workbench_html_includes_a_display_only_live_run_view(self):
        from app.workbench import WORKBENCH_HTML

        self.assertIn('id="live-run"', WORKBENCH_HTML)
        self.assertIn('id="live-run-stdout"', WORKBENCH_HTML)
        self.assertIn('id="live-run-stderr"', WORKBENCH_HTML)
        self.assertIn('fetch("/api/live-run")', WORKBENCH_HTML)
        self.assertIn('setTimeout(pollLiveRun, 1000)', WORKBENCH_HTML)
        self.assertIn('payload.state === "terminal" || payload.state === "inactive"', WORKBENCH_HTML)
        self.assertIn('await renderDecisionQueue();', WORKBENCH_HTML)
        self.assertNotIn('/api/live-run", {\n        method:', WORKBENCH_HTML)

    def test_historical_runs_are_rederived_after_new_evidence_appears(self):
        first_id = '20260712-010203-000001'
        second_id = '20260712-010203-000002'
        workbench, root = self.make_workbench()
        self.write_target_run_evidence(root, first_id)

        first_history = workbench.historical_captured_runs()
        self.write_target_run_evidence(root, second_id)
        second_history = workbench.historical_captured_runs()

        self.assertEqual([entry.run_id for entry in first_history], [first_id])
        self.assertEqual([entry.run_id for entry in second_history], [second_id, first_id])

    def test_operator_decision_queue_derives_every_stage_read_only(self):
        awaiting_verification_id = '20260719-010203-000001'
        awaiting_review_id = '20260719-010203-000002'
        retry_id = '20260719-010203-000003'
        superseded_id = '20260719-010203-000004'
        evidence_problem_id = '20260719-010203-000005'
        failed_verification_id = '20260719-010203-000006'
        workbench, root = self.make_workbench()

        for issue_number in (49, 50, 51, 52, 53):
            workbench.approve_draft(self.approval_payload(issue_number=issue_number))

        self.write_target_run_evidence(
            root,
            awaiting_verification_id,
            {
                'run_id': awaiting_verification_id,
                'run_status': 'COMPLETED',
                'failure_reason': None,
                'agent': 'codex',
                'delegation_task_file': 'tasks/workbench-issue-49.task.md',
            },
        )
        review_run = self.write_target_run_evidence(
            root,
            awaiting_review_id,
            {
                'run_id': awaiting_review_id,
                'run_status': 'COMPLETED',
                'failure_reason': None,
                'agent': 'codex',
                'delegation_task_file': 'tasks/workbench-issue-50.task.md',
            },
        )
        review_run.joinpath('verify.json').write_text(
            json.dumps({'status': 'PASS', 'acceptance': {'returncode': 0}}), encoding='utf-8'
        )
        self.write_target_run_evidence(
            root,
            retry_id,
            {
                'run_id': retry_id,
                'run_status': 'FAILED',
                'failure_reason': 'adapter_unavailable',
                'agent': 'codex',
                'delegation_task_file': 'tasks/workbench-issue-51.task.md',
            },
        )
        self.write_target_run_evidence(
            root,
            superseded_id,
            {
                'run_id': superseded_id,
                'run_status': 'COMPLETED',
                'failure_reason': None,
                'agent': 'codex',
                'delegation_task_file': 'tasks/workbench-issue-51.task.md',
                'superseded_by_run_id': retry_id,
                'superseded_reason': 'newer_delegation_target_base',
            },
        )
        failed_verification_run = self.write_target_run_evidence(
            root,
            failed_verification_id,
            {
                'run_id': failed_verification_id,
                'run_status': 'COMPLETED',
                'failure_reason': None,
                'agent': 'codex',
                'delegation_task_file': 'tasks/workbench-issue-53.task.md',
            },
        )
        failed_verification_run.joinpath('verify.json').write_text(
            json.dumps(
                {
                    'status': 'FAIL',
                    'reason': 'target_acceptance_failed',
                    'acceptance': {'returncode': 1},
                }
            ),
            encoding='utf-8',
        )
        (root / 'runs' / evidence_problem_id).mkdir(parents=True)

        status_before_queue = subprocess.check_output(
            ['git', '-C', str(root), 'status', '--porcelain'], text=True
        )
        first_queue = workbench.operator_decision_queue()
        second_queue = workbench.operator_decision_queue()

        self.assertEqual(first_queue, second_queue)
        self.assertEqual(first_queue.authority, 'operator_decision_queue')
        stages = {stage.name: stage.items for stage in first_queue.stages}
        self.assertEqual(
            [stage.name for stage in first_queue.stages],
            [
                'planning_proposals',
                'awaiting_execution',
                'executing',
                'awaiting_verification',
                'awaiting_promotion_review',
                'awaiting_promotion',
                'retry_decision',
                'evidence_problems',
            ],
        )
        self.assertEqual([item.task_file for item in stages['awaiting_execution']], ['tasks/workbench-issue-52.task.md'])
        self.assertEqual(stages['executing'], [])
        self.assertEqual([item.run_id for item in stages['awaiting_verification']], [awaiting_verification_id])
        self.assertEqual([item.task_file for item in stages['awaiting_verification']], ['tasks/workbench-issue-49.task.md'])
        self.assertEqual([item.run_id for item in stages['awaiting_promotion_review']], [awaiting_review_id])
        review_item = stages['awaiting_promotion_review'][0]
        self.assertIn('acceptance PASS', review_item.evidence_line)
        self.assertIn('changed paths app/widget.py', review_item.evidence_line)
        self.assertEqual([item.run_id for item in stages['retry_decision']], [failed_verification_id, retry_id])
        retry_items = {item.run_id: item for item in stages['retry_decision']}
        self.assertEqual(retry_items[retry_id].failure_reason, 'adapter_unavailable')
        self.assertEqual(retry_items[failed_verification_id].failure_reason, 'target_acceptance_failed')
        self.assertIn('target_acceptance_failed', retry_items[failed_verification_id].evidence_line)
        self.assertEqual([item.run_id for item in stages['evidence_problems']], [evidence_problem_id])
        self.assertEqual(stages['evidence_problems'][0].evidence_error, 'captured_run_record_unavailable')
        self.assertNotIn(superseded_id, [item.run_id for stage in first_queue.stages for item in stage.items])
        self.assertEqual(
            subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain'], text=True),
            status_before_queue,
        )

        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(workbench))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(f'http://127.0.0.1:{server.server_port}/api/decision-queue') as response:
                payload = json.loads(response.read().decode('utf-8'))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(payload, asdict(first_queue))
        self.assertEqual(
            subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain'], text=True),
            status_before_queue,
        )

    def test_operator_decision_queue_excludes_runs_with_committed_promotion_review(self):
        run_id = '20260719-010203-000007'
        workbench, root = self.make_workbench()
        run_dir = self.write_target_run_evidence(
            root,
            run_id,
            {
                'run_id': run_id,
                'run_status': 'COMPLETED',
                'failure_reason': None,
                'agent': 'codex',
                'run_mode': 'target',
                'patch_sha256': 'b' * 64,
            },
        )
        run_dir.joinpath('verify.json').write_text(
            json.dumps({'status': 'PASS', 'acceptance': {'returncode': 0}}), encoding='utf-8'
        )
        review_path = root / 'reviews' / 'promotion' / f'{run_id}.json'
        review_path.parent.mkdir(parents=True)
        review_path.write_text(
            json.dumps(
                {
                    'schema_version': 1,
                    'review_type': 'promotion',
                    'run_id': run_id,
                    'patch_sha256': 'b' * 64,
                    'reviewer': 'operator',
                    'decision': 'APPROVED',
                    'concerns': 'No concerns.',
                    'follow_up_tasks': [],
                    'evidence_attestation': True,
                }
            ),
            encoding='utf-8',
        )
        subprocess.run(['git', '-C', str(root), 'add', 'reviews/promotion'], check=True)
        subprocess.run(['git', '-C', str(root), 'commit', '-q', '-m', 'Record promotion review'], check=True)

        stages = {stage.name: stage.items for stage in workbench.operator_decision_queue().stages}

        self.assertEqual(stages['awaiting_promotion_review'], [])
        promotion_item = stages['awaiting_promotion'][0]
        self.assertEqual(promotion_item.reviewer, 'operator')
        self.assertEqual(promotion_item.review_decision, 'APPROVED')
        self.assertEqual(promotion_item.review_concerns, 'No concerns.')
        self.assertTrue(promotion_item.promotion_review_revision)
        self.assertEqual(promotion_item.current_blocker, 'forge_repo_dirty')

    def test_operator_decision_queue_renders_all_stages_when_empty(self):
        workbench, _ = self.make_workbench()

        queue = workbench.operator_decision_queue()

        self.assertEqual(
            [(stage.name, stage.label, stage.items) for stage in queue.stages],
            [
                ('awaiting_execution', 'Awaiting execution', []),
                ('executing', 'Executing', []),
                ('awaiting_verification', 'Awaiting verification', []),
                ('awaiting_promotion_review', 'Verified, awaiting promotion review', []),
                ('awaiting_promotion', 'Promotion-ready, awaiting promotion', []),
                ('retry_decision', 'Retry decision', []),
                ('evidence_problems', 'Evidence problems', []),
            ],
        )

    def test_operator_decision_queue_renders_all_stages_when_empty(self):
        workbench, _ = self.make_workbench()

        queue = workbench.operator_decision_queue()

        self.assertEqual(
            [(stage.name, stage.label, stage.items) for stage in queue.stages],
            [
                ('planning_proposals', 'Planning proposals awaiting approval', []),
                ('awaiting_execution', 'Awaiting execution', []),
                ('executing', 'Executing', []),
                ('awaiting_verification', 'Awaiting verification', []),
                ('awaiting_promotion_review', 'Verified, awaiting promotion review', []),
                ('awaiting_promotion', 'Promotion-ready, awaiting promotion', []),
                ('retry_decision', 'Retry decision', []),
                ('evidence_problems', 'Evidence problems', []),
            ],
        )

    def test_workbench_html_makes_the_operator_decision_queue_the_home_view(self):
        from app.workbench import WORKBENCH_HTML

        self.assertIn('Operator decision queue', WORKBENCH_HTML)
        self.assertIn('Nothing awaiting a decision is invisible.', WORKBENCH_HTML)
        self.assertIn('fetch("/api/decision-queue")', WORKBENCH_HTML)
        self.assertIn('Prepare a new task', WORKBENCH_HTML)
        self.assertIn('Historical captured runs', WORKBENCH_HTML)
        self.assertIn('item.action_label', WORKBENCH_HTML)
        self.assertIn('item.action === "inspect_evidence"', WORKBENCH_HTML)
        self.assertIn('renderEvidenceDetails(item.run_id)', WORKBENCH_HTML)

    def test_workbench_html_renders_a_dedicated_structured_promotion_review_form(self):
        from app.workbench import WORKBENCH_HTML

        for field in (
            'Promotion review',
            'Reviewer',
            'APPROVED',
            'CHANGES_REQUESTED',
            'NO_CONCERNS',
            'I attest that I reviewed the displayed run, patch, and evidence.',
            'fetch("/api/promotion-reviews"',
            'evidence_attestation: attestation.checked',
            'Promotion in progress',
            'promotion_record',
            'diagnostics',
            'item.review_decision',
            'item.current_blocker',
        ):
            self.assertIn(field, WORKBENCH_HTML)

    def test_promotion_review_submission_commits_an_immutable_exact_run_review(self):
        run_id = '20260722-010203-000111'
        patch_sha256 = 'c' * 64
        workbench, root = self.make_workbench()
        (root / '.gitignore').write_text('runs/\ntarget/\n', encoding='utf-8')
        subprocess.run(['git', '-C', str(root), 'add', '.gitignore'], check=True)
        subprocess.run(['git', '-C', str(root), 'commit', '-q', '-m', 'Ignore captured evidence'], check=True)
        run_dir = self.write_target_run_evidence(
            root, run_id,
            {'run_id': run_id, 'run_status': 'COMPLETED', 'failure_reason': None,
             'agent': 'codex', 'run_mode': 'target', 'patch_sha256': patch_sha256},
        )
        run_dir.joinpath('verify.json').write_text(
            json.dumps({'status': 'PASS', 'acceptance': {'returncode': 0}}), encoding='utf-8'
        )

        preparation = workbench.prepare_promotion_review({'run_id': run_id})
        self.assertEqual(preparation.patch_sha256, patch_sha256)
        submission = workbench.submit_promotion_review({
            'run_id': run_id, 'patch_sha256': patch_sha256, 'reviewer': 'operator',
            'decision': 'APPROVED', 'concerns': 'NO_CONCERNS', 'follow_up_tasks': [],
            'evidence_attestation': True,
        })

        review_path = root / 'reviews' / 'promotion' / f'{run_id}.json'
        self.assertEqual(submission.run_id, run_id)
        self.assertTrue(review_path.is_file())
        self.assertEqual(json.loads(review_path.read_text(encoding='utf-8'))['patch_sha256'], patch_sha256)
        with self.assertRaises(WorkbenchPromotionReviewError) as caught:
            workbench.submit_promotion_review({
                'run_id': run_id, 'patch_sha256': patch_sha256, 'reviewer': 'operator',
                'decision': 'APPROVED', 'concerns': 'NO_CONCERNS', 'follow_up_tasks': [],
                'evidence_attestation': True,
            })
        self.assertEqual(str(caught.exception), 'promotion_review_already_exists')

    def test_promotion_review_submission_rechecks_current_target_base(self):
        run_id = '20260722-010203-000112'
        patch_sha256 = 'd' * 64
        workbench, root = self.make_workbench()
        (root / '.gitignore').write_text('runs/\ntarget/\n', encoding='utf-8')
        subprocess.run(['git', '-C', str(root), 'add', '.gitignore'], check=True)
        subprocess.run(['git', '-C', str(root), 'commit', '-q', '-m', 'Ignore captured evidence'], check=True)
        target = root / 'target'
        subprocess.run(['git', 'init', '-q', str(target)], check=True)
        subprocess.run(['git', '-C', str(target), 'config', 'user.email', 'target@example.invalid'], check=True)
        subprocess.run(['git', '-C', str(target), 'config', 'user.name', 'Target'], check=True)
        (target / 'README.md').write_text('base\n', encoding='utf-8')
        subprocess.run(['git', '-C', str(target), 'add', 'README.md'], check=True)
        subprocess.run(['git', '-C', str(target), 'commit', '-q', '-m', 'base'], check=True)
        base_sha = subprocess.check_output(['git', '-C', str(target), 'rev-parse', 'HEAD'], text=True).strip()
        run_dir = self.write_target_run_evidence(root, run_id, {
            'run_id': run_id, 'run_status': 'COMPLETED', 'failure_reason': None,
            'agent': 'codex', 'run_mode': 'target', 'patch_sha256': patch_sha256,
            'target_repo': str(target), 'target_base_branch': 'master',
            'target_base_sha': base_sha, 'delegation_target_base_sha': base_sha,
        })
        run_dir.joinpath('verify.json').write_text(json.dumps({'status': 'PASS', 'acceptance': {'returncode': 0}}), encoding='utf-8')
        workbench.prepare_promotion_review({'run_id': run_id})
        (target / 'README.md').write_text('advanced\n', encoding='utf-8')
        subprocess.run(['git', '-C', str(target), 'add', 'README.md'], check=True)
        subprocess.run(['git', '-C', str(target), 'commit', '-q', '-m', 'advance target'], check=True)
        with self.assertRaises(WorkbenchPromotionReviewError) as caught:
            workbench.submit_promotion_review({
                'run_id': run_id, 'patch_sha256': patch_sha256, 'reviewer': 'operator',
                'decision': 'APPROVED', 'concerns': 'NO_CONCERNS', 'follow_up_tasks': [],
                'evidence_attestation': True,
            })
        self.assertEqual(str(caught.exception), 'stale_delegation_target_base')

    def test_workbench_html_hosts_planning_sessions_and_zero_authority_proposal_handoff(self):
        from app.workbench import WORKBENCH_HTML

        self.assertIn('Start planning session', WORKBENCH_HTML)
        self.assertIn('id="planning-workflow"', WORKBENCH_HTML)
        self.assertIn('id="planning-session-list"', WORKBENCH_HTML)
        self.assertIn('id="planning-transcript"', WORKBENCH_HTML)
        self.assertIn('fetch("/api/planning-sessions"', WORKBENCH_HTML)
        self.assertIn('/api/planning-sessions/${selectedPlanningSession.session_id}/messages', WORKBENCH_HTML)
        self.assertIn('/api/planning-sessions/${selectedPlanningSession.session_id}/close', WORKBENCH_HTML)
        self.assertIn('planning_session_id: selectedPlanningProposal ? selectedPlanningProposal.session_id : null', WORKBENCH_HTML)
        self.assertIn('planning_proposal_version: selectedPlanningProposal ? selectedPlanningProposal.version : null', WORKBENCH_HTML)
        self.assertIn('session.state !== "BOUNDARY_VIOLATION"', WORKBENCH_HTML)
        self.assertIn('item.action === "review_planning_proposal"', WORKBENCH_HTML)
        self.assertIn('newestValidVersion', WORKBENCH_HTML)
        self.assertIn('newest valid (default)', WORKBENCH_HTML)

    def test_operator_decision_queue_surfaces_the_active_delegation(self):
        started = Event()
        release = Event()
        run_id = '20260719-020304-000001'

        def target_runner(command, root):
            started.set()
            self.assertTrue(release.wait(timeout=5))
            self.write_run_record(root, run_id)
            return subprocess.CompletedProcess(command, 0, f'RUN_CAPTURED: {run_id}\n', '')

        workbench, _ = self.make_workbench(target_runner=target_runner)
        self.approve_delegation(workbench)
        execution = Thread(target=lambda: workbench.execute_confirmed_delegation(self.execute_payload()))
        execution.start()
        self.assertTrue(started.wait(timeout=5))
        try:
            stages = {stage.name: stage.items for stage in workbench.operator_decision_queue().stages}
            self.assertEqual(stages['awaiting_execution'], [])
            self.assertEqual([item.task_file for item in stages['executing']], ['tasks/workbench-issue-49.task.md'])
            self.assertEqual([item.adapter for item in stages['executing']], ['codex'])
        finally:
            release.set()
            execution.join(timeout=5)

        self.assertFalse(execution.is_alive())

if __name__ == "__main__":
    unittest.main()
