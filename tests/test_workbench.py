import json
import unittest
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import urlopen

from app.workbench import (
    IssueContext,
    IssueReference,
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


if __name__ == "__main__":
    unittest.main()
