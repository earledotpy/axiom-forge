import json
import subprocess
import unittest
from pathlib import Path

from app.planning_drivers import ClaudePlanningDriver, CodexPlanningDriver, fixed_policy_identity


class RecordingRunner:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, command, *, cwd, env):
        self.calls.append((command, cwd, env))
        return self.responses.pop(0)


class TestPlanningDrivers(unittest.TestCase):
    def test_cli_drivers_fail_closed_without_host_enforced_confinement(self):
        self.assertFalse(CodexPlanningDriver.capabilities["host_enforced_confinement"])
        self.assertFalse(ClaudePlanningDriver.capabilities["host_enforced_confinement"])

    def test_codex_uses_read_only_json_transport_and_normalizes_resume_and_proposal(self):
        records = [
            {"type": "thread.started", "thread_id": "codex-thread"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps({
                "task_text": "Do the bounded work.",
                "target_scope": ["app/change.py"],
                "acceptance_check": "echo checked",
                "suggested_adapter": "codex",
            })}},
            {"type": "turn.completed"},
        ]
        runner = RecordingRunner([
            subprocess.CompletedProcess(["codex", "--version"], 0, "codex-cli 1.2.3\n", ""),
            subprocess.CompletedProcess(["codex", "exec"], 0, "\n".join(json.dumps(record) for record in records), ""),
            subprocess.CompletedProcess(
                ["codex", "exec", "resume"],
                0,
                json.dumps({"type": "turn.completed"}),
                "",
            ),
        ])
        driver = CodexPlanningDriver(runner=runner)

        result = driver.start(
            session_id="forge-session",
            worktree=Path("C:/target-worktree"),
            policy={"name": "investigation-only-v1"},
            seed={"kind": "free_form"},
            prompt="Investigate.",
        )

        command = runner.calls[1][0]
        self.assertEqual(driver.identity(), "codex-cli 1.2.3")
        self.assertIn("--sandbox", command)
        self.assertIn("read-only", command)
        self.assertIn("--json", command)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)
        self.assertEqual(result["resume_identity"], "codex-thread")
        driver.resume(
            resume_identity=result["resume_identity"],
            worktree=Path("C:/target-worktree"),
            policy={"name": "investigation-only-v1"},
        )
        driver.send(
            resume_identity=result["resume_identity"],
            message="Continue.",
            policy={"name": "investigation-only-v1"},
        )
        self.assertIn('sandbox_mode="read-only"', runner.calls[2][0])
        event_types = [event["type"] for event in driver.events(result)]
        self.assertIn("message", event_types)
        self.assertIn("proposal", event_types)
        self.assertEqual(event_types[-1], "idle")

    def test_claude_uses_fixed_tool_policy_and_resumes_the_recorded_vendor_session(self):
        start_records = [
            {"type": "system", "subtype": "init", "session_id": "claude-session"},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "What outcome matters?"}]}},
            {"type": "result", "subtype": "success", "session_id": "claude-session"},
        ]
        resume_records = [
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "Understood."}]}},
            {"type": "result", "subtype": "success", "session_id": "claude-session"},
        ]
        runner = RecordingRunner([
            subprocess.CompletedProcess(["claude", "--version"], 0, "2.1.215 (Claude Code)\n", ""),
            subprocess.CompletedProcess(["claude", "-p"], 0, "\n".join(json.dumps(record) for record in start_records), ""),
            subprocess.CompletedProcess(["claude", "-p"], 0, "\n".join(json.dumps(record) for record in resume_records), ""),
        ])
        driver = ClaudePlanningDriver(runner=runner)
        policy = {"name": "investigation-only-v1"}

        started = driver.start(
            session_id="forge-session",
            worktree=Path("C:/target-worktree"),
            policy=policy,
            seed={"kind": "free_form"},
            prompt="Investigate.",
        )
        driver.resume(
            resume_identity=started["resume_identity"],
            worktree=Path("C:/target-worktree"),
            policy=policy,
        )
        resumed = driver.send(
            resume_identity=started["resume_identity"],
            message="The outcome is safety.",
            policy=policy,
        )

        start_command = runner.calls[1][0]
        resume_command = runner.calls[2][0]
        self.assertIn("--permission-mode", start_command)
        self.assertIn("plan", start_command)
        self.assertIn("--allowedTools", start_command)
        self.assertIn("--resume", resume_command)
        self.assertIn("claude-session", resume_command)
        self.assertIn("Bash(git status *)", " ".join(start_command))
        self.assertEqual(resumed["resume_identity"], "claude-session")
        self.assertEqual(fixed_policy_identity(policy), fixed_policy_identity(dict(policy)))
