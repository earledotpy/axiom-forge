import json
import tempfile
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.workbench import WORKBENCH_HTML, IssueContext, WorkbenchExecutionError, WorkbenchServer, make_handler


FIXTURE_ISSUE = IssueContext(
    number=55,
    title="Guard first-workbench safety boundaries",
    body="Keep the local workbench inside its first-version boundary.",
    url="https://github.com/earledotpy/axiom-forge/issues/55",
    repo="earledotpy/axiom-forge",
)


class TestWorkbenchBoundaries(unittest.TestCase):
    def make_workbench(self, root: Path, target_runner=None) -> WorkbenchServer:
        return WorkbenchServer(lambda reference: FIXTURE_ISSUE, forge_root=root, target_runner=target_runner)

    def assert_post_not_found(self, server: ThreadingHTTPServer, path: str) -> None:
        request = Request(
            f"http://127.0.0.1:{server.server_port}{path}",
            data=json.dumps({}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as caught:
            urlopen(request)
        self.assertEqual(caught.exception.code, 404)

    def test_promotion_and_qualification_are_not_workbench_routes(self):
        self.assertNotIn("promotion", WORKBENCH_HTML.casefold())
        self.assertNotIn("qualification", WORKBENCH_HTML.casefold())
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.make_workbench(root)))
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                self.assert_post_not_found(server, "/api/promote")
                self.assert_post_not_found(server, "/api/qualification")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_execution_rejects_a_generic_command_without_starting_a_runner(self):
        calls = []
        with tempfile.TemporaryDirectory() as temporary_directory:
            workbench = self.make_workbench(Path(temporary_directory), lambda command, root: calls.append(command))
            with self.assertRaises(WorkbenchExecutionError) as caught:
                workbench.execute_confirmed_delegation({"command": "bash scripts/promote.sh", "confirmed": True})
        self.assertEqual(str(caught.exception), "generic_command_execution_forbidden")
        self.assertEqual(calls, [])

    def test_retry_requires_explicit_confirmation_without_starting_a_runner(self):
        calls = []
        with tempfile.TemporaryDirectory() as temporary_directory:
            workbench = self.make_workbench(Path(temporary_directory), lambda command, root: calls.append(command))
            with self.assertRaises(WorkbenchExecutionError) as caught:
                workbench.retry_confirmed_delegation(
                    {"run_id": "20260712-010203-000001", "adapter": "codex", "confirmed": False}
                )
        self.assertEqual(str(caught.exception), "operator_retry_confirmation_required")
        self.assertEqual(calls, [])

    def test_second_delegation_is_rejected_while_the_first_is_active(self):
        started = Event()
        release = Event()
        first_result = []

        def target_runner(command, root):
            started.set()
            self.assertTrue(release.wait(timeout=5))
            raise OSError("fixture runner interrupted")

        def run_first_delegation(workbench):
            try:
                workbench._run_confirmed_delegation("tasks/one.task.md", "codex")
            except BaseException as error:
                first_result.append(error)

        with tempfile.TemporaryDirectory() as temporary_directory:
            workbench = self.make_workbench(Path(temporary_directory), target_runner)
            first = Thread(target=run_first_delegation, args=(workbench,))
            first.start()
            self.assertTrue(started.wait(timeout=5))
            with self.assertRaises(WorkbenchExecutionError) as caught:
                workbench._run_confirmed_delegation("tasks/two.task.md", "codex")
            release.set()
            first.join(timeout=5)
        self.assertEqual(str(caught.exception), "active_workbench_delegation_in_progress")
        self.assertFalse(first.is_alive())
        self.assertEqual(len(first_result), 1)
        self.assertIsInstance(first_result[0], WorkbenchExecutionError)
        self.assertEqual(str(first_result[0]), "target_mode_runner_start_failed")

    def test_preview_creates_no_database_or_other_persistent_state(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            preview = self.make_workbench(root).preview_for_issue("55")
            self.assertEqual(preview.authority, "draft_only")
            self.assertEqual(list(root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
