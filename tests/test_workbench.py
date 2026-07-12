import json
import subprocess
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

if __name__ == "__main__":
    unittest.main()
