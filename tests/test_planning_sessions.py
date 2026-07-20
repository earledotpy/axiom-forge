import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from app.planning_sessions import PlanningSessionError, PlanningSessionStore


class FakeDriver:
    def __init__(self, events):
        self.events = events

    def start(self, *, session_id, worktree, policy, seed, resume_identity=None):
        return {"resume_identity": f"resume-{session_id}", "events": self.events}

    def send(self, *, resume_identity, message, policy):
        return {"resume_identity": resume_identity, "events": self.events}

    def close(self, *, resume_identity):
        return []


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
