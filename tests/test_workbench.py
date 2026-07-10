import json
import subprocess
import tempfile
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.request import Request, urlopen

from scripts.delegation_artifact_set import load_task_artifact_set

from app.workbench import (
    IssueContext,
    IssueReference,
    WorkbenchApprovalError,
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
    def make_workbench(self) -> tuple[WorkbenchServer, Path]:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "Axiom Test"], check=True)
        (root / "README.md").write_text("fixture\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "fixture"], check=True)
        return WorkbenchServer(lambda reference: FIXTURE_ISSUE, forge_root=root), root

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


if __name__ == "__main__":
    unittest.main()
