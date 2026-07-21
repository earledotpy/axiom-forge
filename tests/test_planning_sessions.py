import json
import subprocess
import tempfile
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread
from urllib.request import Request, urlopen

from app.planning_sessions import PlanningSessionError, PlanningSessionStore
from app.planning_drivers import REQUIRED_PLANNING_CAPABILITIES, planning_driver_registry
from app.workbench_models import IssueContext
from app.workbench_runtime import WorkbenchServer
from app.workbench_http import make_handler


class FakeDriver:
    capabilities = {name: True for name in REQUIRED_PLANNING_CAPABILITIES}

    def __init__(self, events):
        self._events = events

    def start(self, *, session_id, worktree, policy, seed, prompt, resume_identity=None):
        return {"resume_identity": f"resume-{session_id}", "events": self._events}

    def send(self, *, resume_identity, message, policy):
        return {"resume_identity": resume_identity, "events": self._events}

    def events(self, result):
        return result["events"]

    def resume(self, *, resume_identity, worktree, policy):
        return resume_identity

    def close(self, *, resume_identity):
        return []

    def identity(self):
        return "fake-driver 1.0"


class ActiveFakeDriver(FakeDriver):
    def start(self, *, session_id, worktree, policy, seed, prompt, resume_identity=None):
        return {
            "resume_identity": f"resume-{session_id}",
            "events": [{"sequence": 1, "type": "message", "text": "Still working."}],
        }


class IncrementalFakeDriver(FakeDriver):
    background_turns = True

    def __init__(self, events):
        super().__init__(events)
        self.start_release = Event()
        self.send_release = Event()

    def start(self, *, session_id, worktree, policy, seed, prompt, resume_identity=None, event_sink=None):
        proposal = {
            "task_text": "Bounded incremental task.",
            "target_scope": ["README.md"],
            "acceptance_check": "test -f README.md",
            "suggested_adapter": "fake-a",
        }
        events = [
            {"sequence": 1, "type": "message", "text": "Still investigating."},
            {"sequence": 2, "type": "proposal", "proposal": proposal},
            {"sequence": 3, "type": "idle"},
        ]
        if event_sink is None:
            self.start_release.wait(1)
            return {"resume_identity": f"resume-{session_id}", "events": events}
        event_sink(events[0])
        event_sink(events[1])
        self.start_release.wait(5)
        event_sink(events[2])
        return {"resume_identity": f"resume-{session_id}", "events": []}

    def send(self, *, resume_identity, message, policy, event_sink=None):
        events = [
            {"sequence": 1, "type": "message", "text": "Refining the plan."},
            {"sequence": 2, "type": "idle"},
        ]
        if event_sink is None:
            self.send_release.wait(1)
            return {"resume_identity": resume_identity, "events": events}
        event_sink(events[0])
        self.send_release.wait(5)
        event_sink(events[1])
        return {"resume_identity": resume_identity, "events": []}

    def close(self, *, resume_identity, session_id=None):
        self.start_release.set()
        self.send_release.set()
        return {"resume_identity": resume_identity, "session_id": session_id, "closed": True}




class IdentityFailureDriver(FakeDriver):
    def identity(self):
        raise RuntimeError("identity unavailable")


class TwoTurnDriver(FakeDriver):
    """A driver that emits one event stream on start and another on resume/send."""

    def __init__(self, start_events, send_events):
        super().__init__(start_events)
        self._send_events = send_events

    def send(self, *, resume_identity, message, policy):
        return {"resume_identity": resume_identity, "events": self._send_events}


def _queued_runner(responses):
    queue = list(responses)

    def run(command, *, cwd, env):
        return queue.pop(0)

    return run


class TestPlanningSessions(unittest.TestCase):
    def make_target(self, root):
        target = root / "target"
        subprocess.run(["git", "init", "-q", str(target)], check=True)
        subprocess.run(["git", "-C", str(target), "config", "user.email", "test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(target), "config", "user.name", "Axiom Test"], check=True)
        target.joinpath("README.md").write_text("target\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(target), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(target), "commit", "-q", "-m", "target"], check=True)
        return target

    def test_start_records_append_only_evidence_and_valid_proposal_without_authority(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            forge = root / 'forge'
            forge.mkdir()
            target = self.make_target(root)
            events = [
                {"sequence": 1, "type": "message", "text": "I inspected the target."},
                {"sequence": 2, "type": "idle"},
                {"sequence": 3, "type": "proposal", "proposal": {
                    "task_text": "Add the target behavior.",
                    "target_scope": ["README.md"],
                    "acceptance_check": "test -f README.md",
                    "suggested_adapter": "fake-b",
                }},
            ]
            store = PlanningSessionStore(forge, {"fake-a": FakeDriver(events), "fake-b": FakeDriver([])})

            session = store.start({"adapter": "fake-a", "target_repo": str(target), "prompt": "Explore it."})

            self.assertEqual(session["state"], "IDLE")
            self.assertEqual(session["authority"], "planning_session")
            session_dir = forge / "sessions" / session["session_id"]
            self.assertTrue(session_dir.joinpath("transcript.jsonl").is_file())
            self.assertTrue(session_dir.joinpath("proposals", "0001.json").is_file())
            self.assertFalse(session_dir.joinpath("receipt.json").exists())
            proposal = store.proposal_for_approval(session["session_id"], 1)
            self.assertEqual(proposal["authority"], "draft_only")
            self.assertEqual(proposal["task_text"], "Add the target behavior.")
            self.assertFalse((forge / "tasks").exists())

    def test_worktree_change_fails_closed_records_receipt_and_removes_worktree(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            forge = root / 'forge'
            forge.mkdir()
            target = self.make_target(root)
            events = [{"sequence": 1, "type": "idle"}]
            store = PlanningSessionStore(forge, {"fake-a": FakeDriver(events), "fake-b": FakeDriver([])})
            session = store.start({"adapter": "fake-a", "target_repo": str(target), "prompt": "Explore it."})
            worktree = Path(store.session(session["session_id"])["worktree"])
            worktree.joinpath("unsafe.txt").write_text("unsafe\n", encoding="utf-8")

            result = store.send(session["session_id"], "Continue.")

            self.assertEqual(result["state"], "BOUNDARY_VIOLATION")
            session_dir = forge / "sessions" / session["session_id"]
            receipt = json.loads(session_dir.joinpath("receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["terminal_status"], "BOUNDARY_VIOLATION")
            self.assertFalse(worktree.exists())
            with self.assertRaises(PlanningSessionError) as caught:
                store.proposal_for_approval(session["session_id"], 1)
            self.assertEqual(str(caught.exception), "planning_session_not_eligible_for_approval")

    def test_policy_request_is_denied_and_recorded_without_driver_permission_escalation(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            forge = root / 'forge'
            forge.mkdir()
            target = self.make_target(root)
            store = PlanningSessionStore(forge, {"fake-a": FakeDriver([{"sequence": 1, "type": "idle"}]), "fake-b": FakeDriver([])})
            session = store.start({"adapter": "fake-a", "target_repo": str(target), "prompt": "Explore it."})

            with self.assertRaises(PlanningSessionError) as caught:
                store.send(session["session_id"], {"tool_approval": "shell"})

            self.assertEqual(str(caught.exception), "planning_policy_change_forbidden")
            transcript = (forge / "sessions" / session["session_id"] / "transcript.jsonl").read_text(encoding="utf-8")
            self.assertIn("policy_denied", transcript)

    def test_issue_seed_is_fetched_read_only_and_preserved_as_a_source_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            forge = root / "forge"
            forge.mkdir()
            target = self.make_target(root)
            requested = []
            issue = IssueContext(
                number=100,
                title="Plan the bounded change",
                body="Body used for planning.",
                url="https://github.com/example/project/issues/100",
                repo="example/project",
                comments=({"author": "operator", "body": "Keep it narrow.", "url": "https://example.test/comment"},),
            )
            store = PlanningSessionStore(forge, {"fake-a": FakeDriver([{"sequence": 1, "type": "idle"}])})
            workbench = WorkbenchServer(
                lambda reference: requested.append(reference) or issue,
                default_repo="example/project",
                forge_root=forge,
                planning_sessions=store,
            )

            session = workbench.start_planning_session({
                "adapter": "fake-a",
                "target_repo": str(target),
                "prompt": "Investigate this issue.",
                "issue_seed": "100",
            })

            self.assertEqual(requested[0].number, 100)
            source_path = forge / "sessions" / session["session_id"] / "source.json"
            source = json.loads(source_path.read_text(encoding="utf-8"))
            self.assertEqual(source["kind"], "github_issue")
            self.assertEqual(source["issue"]["body"], "Body used for planning.")
            self.assertEqual(source["issue"]["comments"][0]["body"], "Keep it narrow.")
            self.assertEqual(len(source["body_sha256"]), 64)

    def test_driver_contract_rejects_each_missing_mandatory_capability(self):
        class MissingCapabilityDriver(FakeDriver):
            pass

        with tempfile.TemporaryDirectory() as temporary_directory:
            for capability in set(REQUIRED_PLANNING_CAPABILITIES) - {"host_enforced_confinement"}:
                driver = MissingCapabilityDriver([])
                driver.capabilities = {name: True for name in REQUIRED_PLANNING_CAPABILITIES}
                driver.capabilities[capability] = False
                with self.subTest(capability=capability):
                    with self.assertRaises(PlanningSessionError) as caught:
                        PlanningSessionStore(Path(temporary_directory), {"incomplete": driver})
                    self.assertEqual(str(caught.exception), "planning_driver_contract_violation")

    def test_production_driver_registry_uses_store_owned_worktree_confinement(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = PlanningSessionStore(Path(temporary_directory), planning_driver_registry())

            self.assertEqual(set(store.drivers), {"codex", "claude-code"})

    def test_selected_proposal_is_recorded_as_zero_authority_approval_provenance(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            forge = root / "forge"
            forge.mkdir()
            subprocess.run(["git", "init", "-q", str(forge)], check=True)
            subprocess.run(["git", "-C", str(forge), "config", "user.email", "test@example.invalid"], check=True)
            subprocess.run(["git", "-C", str(forge), "config", "user.name", "Axiom Test"], check=True)
            forge.joinpath(".gitignore").write_text("sessions/\n", encoding="utf-8")
            forge.joinpath("README.md").write_text("forge\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(forge), "add", ".gitignore", "README.md"], check=True)
            subprocess.run(["git", "-C", str(forge), "commit", "-q", "-m", "fixture"], check=True)
            target = self.make_target(root)
            proposal = {
                "task_text": "Original proposed task.",
                "target_scope": ["app/change.py"],
                "acceptance_check": "echo checked",
                "suggested_adapter": "fake-a",
            }
            driver = FakeDriver([
                {"sequence": 1, "type": "proposal", "proposal": proposal},
                {"sequence": 2, "type": "idle"},
            ])
            store = PlanningSessionStore(forge, {"fake-a": driver})
            workbench = WorkbenchServer(lambda reference: None, forge_root=forge, planning_sessions=store)
            session = store.start({"adapter": "fake-a", "target_repo": str(target), "prompt": "Plan it."})
            queue = workbench.operator_decision_queue()
            planning_items = {stage.name: stage.items for stage in queue.stages}["planning_proposals"]
            self.assertEqual(planning_items[0].planning_session_id, session["session_id"])
            self.assertEqual(planning_items[0].planning_proposal_version, 1)

            delegation = workbench.approve_draft({
                "issue_number": 100,
                "task_text": "Operator-edited task.",
                "target_scope": "app/change.py\n",
                "acceptance_check": "#!/usr/bin/env bash\necho checked\n",
                "adapter": "codex",
                "approved": True,
                "planning_session_id": session["session_id"],
                "planning_proposal_version": 1,
            })

            task_text = (forge / delegation.task_file).read_text(encoding="utf-8")
            selected = store.proposal_for_approval(session["session_id"], 1)
            self.assertIn(f"axiom-forge-planning-session: {session['session_id']}", task_text)
            self.assertIn(f"axiom-forge-planning-proposal-sha256: {selected['proposal_sha256']}", task_text)
            self.assertIn("Operator-edited task.", task_text)

    def test_malformed_event_stream_fails_terminal_and_tears_down(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            forge = root / "forge"
            forge.mkdir()
            target = self.make_target(root)
            driver = FakeDriver([{"sequence": 2, "type": "message", "text": "Skipped one."}])
            store = PlanningSessionStore(forge, {"fake-a": driver})

            with self.assertRaises(PlanningSessionError) as caught:
                store.start({"adapter": "fake-a", "target_repo": str(target), "prompt": "Plan it."})

            self.assertEqual(str(caught.exception), "planning_event_stream_invalid")
            session_dir = next((forge / "sessions").iterdir())
            receipt = json.loads((session_dir / "receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["terminal_status"], "FAILED")
            self.assertEqual(receipt["reason"], "planning_driver_contract_violation")
            self.assertFalse((session_dir / "worktree").exists())

    def test_known_secret_exposure_is_redacted_and_fails_terminal(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            forge = root / "forge"
            forge.mkdir()
            target = self.make_target(root)
            driver = FakeDriver([{"sequence": 1, "type": "message", "text": "value secret-123"}])
            store = PlanningSessionStore(forge, {"fake-a": driver}, secret_values=["secret-123"])

            session = store.start({"adapter": "fake-a", "target_repo": str(target), "prompt": "Plan it."})

            self.assertEqual(session["state"], "FAILED")
            transcript = (forge / "sessions" / session["session_id"] / "transcript.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("secret-123", transcript)
            self.assertIn("[redacted]", transcript)
            self.assertEqual(session["terminal_reason"], "planning_secret_exposure")

    def test_operator_entered_secrets_are_scrubbed_from_the_transcript_without_ending_the_session(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            forge = root / "forge"
            forge.mkdir()
            target = self.make_target(root)
            store = PlanningSessionStore(
                forge,
                {"fake-a": FakeDriver([{"sequence": 1, "type": "idle"}])},
                secret_values=["op-secret-9999"],
            )
            session = store.start(
                {"adapter": "fake-a", "target_repo": str(target), "prompt": "Look at op-secret-9999 please."}
            )

            resumed = store.send(session["session_id"], "Remember op-secret-9999 for later.")

            self.assertEqual(resumed["state"], "IDLE")
            transcript = (forge / "sessions" / session["session_id"] / "transcript.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("op-secret-9999", transcript)
            self.assertIn("[redacted]", transcript)

    def test_git_ref_change_is_a_boundary_violation_even_when_files_are_clean(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            forge = root / "forge"
            forge.mkdir()
            target = self.make_target(root)
            driver = FakeDriver([{"sequence": 1, "type": "idle"}])
            store = PlanningSessionStore(forge, {"fake-a": driver})
            session = store.start({"adapter": "fake-a", "target_repo": str(target), "prompt": "Plan it."})
            worktree = Path(session["worktree"])
            subprocess.run(["git", "-C", str(worktree), "branch", "unsafe-planning-ref"], check=True)

            result = store.send(session["session_id"], "Continue.")

            self.assertEqual(result["state"], "BOUNDARY_VIOLATION")

    def test_persisted_idle_session_survives_restart_and_is_resumable_with_a_real_driver(self):
        from app.planning_drivers import CodexPlanningDriver

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            forge = root / "forge"
            forge.mkdir()
            target = self.make_target(root)
            start_responses = [
                subprocess.CompletedProcess(["codex", "--version"], 0, "codex-cli 1.2.3\n", ""),
                subprocess.CompletedProcess(
                    ["codex", "exec"],
                    0,
                    "\n".join(json.dumps(record) for record in [
                        {"type": "thread.started", "thread_id": "codex-thread"},
                        {"type": "turn.completed"},
                    ]),
                    "",
                ),
            ]
            first_store = PlanningSessionStore(
                forge, {"codex": CodexPlanningDriver(runner=_queued_runner(start_responses))}
            )
            session = first_store.start({"adapter": "codex", "target_repo": str(target), "prompt": "Investigate."})
            self.assertEqual(session["state"], "IDLE")

            # A server restart drops the driver's in-memory session map. A fresh
            # store + fresh driver must leave the persisted IDLE session intact
            # (only ACTIVE fails) and still resume it from the recorded identity.
            resume_responses = [
                subprocess.CompletedProcess(
                    ["codex", "exec", "resume"],
                    0,
                    "\n".join(json.dumps(record) for record in [
                        {"type": "item.completed", "item": {"type": "agent_message", "text": "Resumed after restart."}},
                        {"type": "turn.completed"},
                    ]),
                    "",
                ),
            ]
            restarted_store = PlanningSessionStore(
                forge, {"codex": CodexPlanningDriver(runner=_queued_runner(resume_responses))}
            )
            self.assertEqual(restarted_store.session(session["session_id"])["state"], "IDLE")

            resumed = restarted_store.send(session["session_id"], "Continue after restart.")

            self.assertEqual(resumed["state"], "IDLE")
            transcript = (forge / "sessions" / session["session_id"] / "transcript.jsonl").read_text(encoding="utf-8")
            self.assertIn("Resumed after restart.", transcript)

    def test_server_restart_fails_active_session_and_public_view_contains_events(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            forge = root / "forge"
            forge.mkdir()
            target = self.make_target(root)
            driver = ActiveFakeDriver([])
            store = PlanningSessionStore(forge, {"fake-a": driver})
            started = store.start({"adapter": "fake-a", "target_repo": str(target), "prompt": "Plan it."})
            self.assertEqual(started["events"][-1]["text"], "Still working.")

            recovered = PlanningSessionStore(forge, {"fake-a": driver}).session(started["session_id"])

            self.assertEqual(recovered["state"], "FAILED")
            self.assertEqual(recovered["terminal_reason"], "planning_server_restarted")
            self.assertFalse(Path(recovered["worktree"]).exists())

    def test_incremental_driver_start_returns_active_while_events_are_still_arriving(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            forge = root / "forge"
            forge.mkdir()
            target = self.make_target(root)
            driver = IncrementalFakeDriver([])
            store = PlanningSessionStore(forge, {"fake-a": driver})

            started_at = time.monotonic()
            started = store.start({"adapter": "fake-a", "target_repo": str(target), "prompt": "Plan it."})
            elapsed = time.monotonic() - started_at

            self.assertLess(elapsed, 0.8)
            self.assertEqual(started["state"], "ACTIVE")
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline:
                current = store.session(started["session_id"])
                if current["proposals"] and any(event.get("text") == "Still investigating." for event in current["events"]):
                    break
                time.sleep(0.01)
            else:
                self.fail("incremental planning message was not observable while the turn was active")
            with self.assertRaises(PlanningSessionError) as caught:
                store.proposal_for_approval(started["session_id"], 1)
            self.assertEqual(str(caught.exception), "planning_session_not_eligible_for_approval")

            driver.start_release.set()
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if store.session(started["session_id"])["state"] == "IDLE":
                    break
                time.sleep(0.01)
            else:
                self.fail(f"incremental planning turn did not become idle: {store.session(started['session_id'])['state']}")
            self.assertEqual(store.proposal_for_approval(started["session_id"], 1)["task_text"], "Bounded incremental task.")

    def test_incremental_driver_send_returns_active_while_events_are_still_arriving(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            forge = root / "forge"
            forge.mkdir()
            target = self.make_target(root)
            driver = IncrementalFakeDriver([])
            driver.start_release.set()
            store = PlanningSessionStore(forge, {"fake-a": driver})
            started = store.start({"adapter": "fake-a", "target_repo": str(target), "prompt": "Plan it."})
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if store.session(started["session_id"])["state"] == "IDLE":
                    break
                time.sleep(0.01)
            else:
                self.fail("initial planning turn did not become idle")

            sent_at = time.monotonic()
            sent = store.send(started["session_id"], "Refine it.")
            elapsed = time.monotonic() - sent_at

            self.assertLess(elapsed, 0.8)
            self.assertEqual(sent["state"], "ACTIVE")
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline:
                current = store.session(started["session_id"])
                if any(event.get("text") == "Refining the plan." for event in current["events"]):
                    break
                time.sleep(0.01)
            else:
                self.fail("incremental resumed message was not observable while the turn was active")
            driver.send_release.set()
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if store.session(started["session_id"])["state"] == "IDLE":
                    break
                time.sleep(0.01)

            else:
                self.fail("resumed planning turn did not become idle")

    def test_closing_an_active_incremental_turn_waits_for_driver_shutdown_before_teardown(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            forge = root / "forge"
            forge.mkdir()
            target = self.make_target(root)
            driver = IncrementalFakeDriver([])
            store = PlanningSessionStore(forge, {"fake-a": driver})
            started = store.start({"adapter": "fake-a", "target_repo": str(target), "prompt": "Plan it."})
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline:
                current = store.session(started["session_id"])
                if any(event.get("text") == "Still investigating." for event in current["events"]):
                    break
                time.sleep(0.01)
            else:
                self.fail("incremental planning message was not observable before close")

            closed = store.close(started["session_id"])

            self.assertEqual(closed["state"], "CLOSED")
            self.assertFalse(Path(closed["worktree"]).exists())

    def test_http_api_returns_active_and_exposes_incremental_start_and_send_events(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            forge = root / "forge"
            forge.mkdir()
            target = self.make_target(root)
            driver = IncrementalFakeDriver([])
            workbench = WorkbenchServer(
                lambda reference: None,
                forge_root=forge,
                planning_sessions=PlanningSessionStore(forge, {"fake-a": driver}),
            )
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(workbench))
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}/api/planning-sessions"
            try:
                start_request = Request(
                    base_url,
                    data=json.dumps({
                        "adapter": "fake-a", "target_repo": str(target), "prompt": "Plan it.",
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                started_at = time.monotonic()
                with urlopen(start_request) as response:
                    started = json.loads(response.read().decode("utf-8"))
                self.assertLess(time.monotonic() - started_at, 2)
                self.assertEqual(started["state"], "ACTIVE")

                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    with urlopen(f"{base_url}/{started['session_id']}") as response:
                        current = json.loads(response.read().decode("utf-8"))
                    if current["proposals"] and any(
                        event.get("text") == "Still investigating." for event in current["events"]
                    ):
                        break
                    time.sleep(0.01)
                else:
                    self.fail("HTTP GET did not expose incremental start events")

                driver.start_release.set()
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    with urlopen(f"{base_url}/{started['session_id']}") as response:
                        current = json.loads(response.read().decode("utf-8"))
                    if current["state"] == "IDLE":
                        break
                    time.sleep(0.01)
                else:
                    self.fail("HTTP planning start did not become idle")

                send_request = Request(
                    f"{base_url}/{started['session_id']}/messages",
                    data=json.dumps({"message": "Refine it."}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                sent_at = time.monotonic()
                with urlopen(send_request) as response:
                    sent = json.loads(response.read().decode("utf-8"))
                self.assertLess(time.monotonic() - sent_at, 2)
                self.assertEqual(sent["state"], "ACTIVE")

                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    with urlopen(f"{base_url}/{started['session_id']}") as response:
                        current = json.loads(response.read().decode("utf-8"))
                    if any(event.get("text") == "Refining the plan." for event in current["events"]):
                        break
                    time.sleep(0.01)
                else:
                    self.fail("HTTP GET did not expose incremental send events")
                driver.send_release.set()
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    with urlopen(f"{base_url}/{started['session_id']}") as response:
                        current = json.loads(response.read().decode("utf-8"))
                    if current["state"] == "IDLE":
                        break
                    time.sleep(0.01)
                else:
                    self.fail("HTTP planning send did not become idle")

            finally:
                driver.start_release.set()
                driver.send_release.set()
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_http_api_starts_lists_resumes_and_closes_a_planning_session(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            forge = root / "forge"
            forge.mkdir()
            target = self.make_target(root)
            proposal = {
                "task_text": "Bounded task.",
                "target_scope": ["app/change.py"],
                "acceptance_check": "echo checked",
                "suggested_adapter": "fake-a",
            }
            driver = FakeDriver([
                {"sequence": 1, "type": "message", "text": "Planning response."},
                {"sequence": 2, "type": "proposal", "proposal": proposal},
                {"sequence": 3, "type": "idle"},
            ])
            workbench = WorkbenchServer(
                lambda reference: None,
                forge_root=forge,
                planning_sessions=PlanningSessionStore(forge, {"fake-a": driver}),
            )
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(workbench))
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                start_request = Request(
                    f"http://127.0.0.1:{server.server_port}/api/planning-sessions",
                    data=json.dumps({
                        "adapter": "fake-a",
                        "target_repo": str(target),
                        "prompt": "Plan it.",
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(start_request) as response:
                    started = json.loads(response.read().decode("utf-8"))
                with urlopen(f"http://127.0.0.1:{server.server_port}/api/planning-sessions") as response:
                    listing = json.loads(response.read().decode("utf-8"))
                message_request = Request(
                    f"http://127.0.0.1:{server.server_port}/api/planning-sessions/{started['session_id']}/messages",
                    data=json.dumps({"message": "Continue."}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(message_request) as response:
                    resumed = json.loads(response.read().decode("utf-8"))
                close_request = Request(
                    f"http://127.0.0.1:{server.server_port}/api/planning-sessions/{started['session_id']}/close",
                    data=b"{}",
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(close_request) as response:
                    closed = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

            self.assertEqual(listing["authority"], "planning_sessions")
            self.assertEqual(listing["sessions"][0]["session_id"], started["session_id"])
            self.assertEqual(resumed["state"], "IDLE")
            self.assertEqual(resumed["proposals"][0]["valid"], True)
            self.assertEqual(closed["state"], "CLOSED")

    def test_driver_identity_failure_records_terminal_evidence_and_removes_worktree(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            forge = root / "forge"
            forge.mkdir()
            target = self.make_target(root)
            store = PlanningSessionStore(forge, {"broken": IdentityFailureDriver([])})

            with self.assertRaises(PlanningSessionError) as caught:
                store.start({"adapter": "broken", "target_repo": str(target), "prompt": "Plan it."})

            self.assertEqual(str(caught.exception), "planning_driver_start_failed")
            session_dir = next((forge / "sessions").iterdir())
            receipt = json.loads((session_dir / "receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["terminal_status"], "FAILED")
            self.assertFalse((session_dir / "worktree").exists())

    def test_planning_session_starts_while_a_delegation_is_active(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            forge = root / "forge"
            forge.mkdir()
            target = self.make_target(root)
            store = PlanningSessionStore(forge, {"fake-a": FakeDriver([{"sequence": 1, "type": "idle"}])})
            workbench = WorkbenchServer(lambda reference: None, forge_root=forge, planning_sessions=store)
            workbench._active_delegation = ("tasks/workbench-issue-49.task.md", "codex")

            session = workbench.start_planning_session(
                {"adapter": "fake-a", "target_repo": str(target), "prompt": "Plan while a delegation runs."}
            )

            self.assertEqual(session["state"], "IDLE")
            self.assertEqual(workbench._active_delegation, ("tasks/workbench-issue-49.task.md", "codex"))

    def test_tracked_file_change_is_a_boundary_violation(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            forge = root / "forge"
            forge.mkdir()
            target = self.make_target(root)
            store = PlanningSessionStore(forge, {"fake-a": FakeDriver([{"sequence": 1, "type": "idle"}])})
            session = store.start({"adapter": "fake-a", "target_repo": str(target), "prompt": "Plan it."})
            worktree = Path(session["worktree"])
            worktree.joinpath("README.md").write_text("mutated tracked file\n", encoding="utf-8")

            result = store.send(session["session_id"], "Continue.")

            self.assertEqual(result["state"], "BOUNDARY_VIOLATION")
            self.assertEqual(result["terminal_reason"], "planning_worktree_changed")
            self.assertFalse(worktree.exists())

    def test_invalid_proposal_is_evidence_but_cannot_pre_fill_or_reach_the_queue(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            forge = root / "forge"
            forge.mkdir()
            target = self.make_target(root)
            invalid_proposal = {
                "task_text": "Missing an acceptance check.",
                "target_scope": ["README.md"],
                "suggested_adapter": "fake-a",
            }
            driver = FakeDriver([
                {"sequence": 1, "type": "proposal", "proposal": invalid_proposal},
                {"sequence": 2, "type": "idle"},
            ])
            store = PlanningSessionStore(forge, {"fake-a": driver})
            workbench = WorkbenchServer(lambda reference: None, forge_root=forge, planning_sessions=store)
            session = store.start({"adapter": "fake-a", "target_repo": str(target), "prompt": "Plan it."})

            self.assertEqual(session["proposals"][0]["valid"], False)
            with self.assertRaises(PlanningSessionError) as caught:
                store.proposal_for_approval(session["session_id"], 1)
            self.assertEqual(str(caught.exception), "planning_proposal_invalid")
            queue = {stage.name: stage.items for stage in workbench.operator_decision_queue().stages}
            self.assertEqual(queue["planning_proposals"], [])

    def test_versioned_proposals_are_immutable_and_default_to_the_newest_valid(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            forge = root / "forge"
            forge.mkdir()
            target = self.make_target(root)
            first = {
                "task_text": "First bounded task.",
                "target_scope": ["README.md"],
                "acceptance_check": "test -f README.md",
                "suggested_adapter": "fake-a",
            }
            second = {
                "task_text": "Refined bounded task.",
                "target_scope": ["README.md", "docs/plan.md"],
                "acceptance_check": "test -f README.md",
                "suggested_adapter": "fake-a",
            }
            driver = TwoTurnDriver(
                [
                    {"sequence": 1, "type": "proposal", "proposal": first},
                    {"sequence": 2, "type": "idle"},
                ],
                [
                    {"sequence": 1, "type": "proposal", "proposal": second},
                    {"sequence": 2, "type": "idle"},
                ],
            )
            store = PlanningSessionStore(forge, {"fake-a": driver})
            workbench = WorkbenchServer(lambda reference: None, forge_root=forge, planning_sessions=store)
            session = store.start({"adapter": "fake-a", "target_repo": str(target), "prompt": "Plan it."})
            resumed = store.send(session["session_id"], "Refine it.")

            self.assertEqual([proposal["version"] for proposal in resumed["proposals"]], [1, 2])
            session_dir = forge / "sessions" / session["session_id"]
            self.assertTrue(session_dir.joinpath("proposals", "0001.json").is_file())
            self.assertTrue(session_dir.joinpath("proposals", "0002.json").is_file())
            self.assertEqual(store.proposal_for_approval(session["session_id"], 1)["task_text"], "First bounded task.")
            self.assertEqual(store.proposal_for_approval(session["session_id"], 2)["task_text"], "Refined bounded task.")
            queue = {stage.name: stage.items for stage in workbench.operator_decision_queue().stages}
            self.assertEqual(queue["planning_proposals"][0].planning_proposal_version, 2)
