import io
import json
import subprocess
import unittest
from pathlib import Path
from threading import Event, Thread

from app.planning_drivers import ClaudePlanningDriver, CodexPlanningDriver, fixed_policy_identity


class RecordingRunner:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, command, *, cwd, env):
        self.calls.append((command, cwd, env))
        return self.responses.pop(0)


class StreamingProcess:
    def __init__(self, records):
        self.stdout = iter([json.dumps(record) + "\n" for record in records])
        self.stderr = io.StringIO("")
        self.returncode = None

    def wait(self):
        self.returncode = 0
        return self.returncode


class BlockingProcess:
    def __init__(self, record):
        self._line = json.dumps(record) + "\n"
        self._line_emitted = False
        self.stopped = Event()
        self.stdout = self
        self.returncode = None

    def __iter__(self):
        return self

    def __next__(self):
        if not self._line_emitted:
            self._line_emitted = True
            return self._line
        self.stopped.wait(5)
        raise StopIteration

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = -15
        self.stopped.set()

    def kill(self):
        self.terminate()

    def wait(self, timeout=None):
        if not self.stopped.wait(timeout):
            raise subprocess.TimeoutExpired("planning-driver", timeout)
        return self.returncode

class RecordingProcessFactory:
    def __init__(self, process):
        self.process = process

    def __call__(self, command, **kwargs):
        return self.process


class TestPlanningDrivers(unittest.TestCase):
    def test_cli_drivers_fail_closed_without_host_enforced_confinement(self):
        self.assertFalse(CodexPlanningDriver.capabilities["host_enforced_confinement"])
        self.assertFalse(ClaudePlanningDriver.capabilities["host_enforced_confinement"])

    def test_codex_streams_normalized_events_from_the_live_process(self):
        records = [
            {"type": "thread.started", "thread_id": "codex-thread"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "Working through it."}},
            {"type": "turn.completed"},
        ]
        runner = RecordingRunner([
            subprocess.CompletedProcess(["codex", "--version"], 0, "codex-cli 1.2.3\n", ""),
        ])
        driver = CodexPlanningDriver(
            runner=runner,
            process_factory=RecordingProcessFactory(StreamingProcess(records)),
        )
        observed = []

        result = driver.start(
            session_id="forge-session",
            worktree=Path("C:/target-worktree"),
            policy={"name": "investigation-only-v1"},
            seed={"kind": "free_form"},
            prompt="Investigate.",
            event_sink=observed.append,
        )

        self.assertTrue(driver.background_turns)
        self.assertEqual(result, {"resume_identity": "codex-thread", "events": []})
        self.assertEqual([event["sequence"] for event in observed], [1, 2, 3, 4])
        self.assertEqual(observed[1]["text"], "Working through it.")
        self.assertEqual(observed[-1]["type"], "idle")

    def test_close_stops_the_live_planning_process_before_returning(self):
        process = BlockingProcess({"type": "thread.started", "thread_id": "codex-thread"})
        runner = RecordingRunner([
            subprocess.CompletedProcess(["codex", "--version"], 0, "codex-cli 1.2.3\n", ""),
        ])
        driver = CodexPlanningDriver(runner=runner, process_factory=RecordingProcessFactory(process))
        observed = Event()
        errors = []

        def run_turn():
            try:
                driver.start(
                    session_id="forge-session",
                    worktree=Path("C:/target-worktree"),
                    policy={"name": "investigation-only-v1"},
                    seed={"kind": "free_form"},
                    prompt="Investigate.",
                    event_sink=lambda event: observed.set(),
                )
            except RuntimeError as error:
                errors.append(str(error))

        thread = Thread(target=run_turn)
        thread.start()
        self.assertTrue(observed.wait(1))

        closed = driver.close(resume_identity=None, session_id="forge-session")
        thread.join(timeout=1)

        self.assertTrue(process.stopped.is_set())
        self.assertFalse(thread.is_alive())
        self.assertEqual(closed["turns_stopped"], 1)
        self.assertEqual(errors, ["codex_planning_turn_failed"])

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

    def test_driver_resumes_a_persisted_idle_session_after_a_server_restart(self):
        # After a server restart the driver is re-instantiated with an empty
        # in-memory session map, but the spec keeps an IDLE session resumable
        # from its persisted opaque resume identity plus the Forge-owned
        # worktree and policy. Resuming must reconstruct the boundary binding,
        # not fail closed as though the vendor process were lost.
        resume_records = [
            {"type": "thread.started", "thread_id": "codex-thread"},
            {"type": "turn.completed"},
        ]
        runner = RecordingRunner([
            subprocess.CompletedProcess(
                ["codex", "exec", "resume"],
                0,
                "\n".join(json.dumps(record) for record in resume_records),
                "",
            ),
        ])
        restarted = CodexPlanningDriver(runner=runner)
        policy = {"name": "investigation-only-v1"}

        restarted.resume(
            resume_identity="codex-thread",
            worktree=Path("C:/target-worktree"),
            policy=policy,
        )
        resumed = restarted.send(
            resume_identity="codex-thread",
            message="Continue after restart.",
            policy=policy,
        )

        self.assertEqual(resumed["resume_identity"], "codex-thread")

    def test_driver_resume_still_rejects_a_worktree_or_policy_mismatch(self):
        driver = CodexPlanningDriver(runner=RecordingRunner([]))
        driver._sessions["codex-thread"] = (
            Path("C:/target-worktree").resolve(),
            fixed_policy_identity({"name": "investigation-only-v1"}),
        )

        with self.assertRaises(RuntimeError) as caught:
            driver.resume(
                resume_identity="codex-thread",
                worktree=Path("C:/other-worktree"),
                policy={"name": "investigation-only-v1"},
            )

        self.assertEqual(str(caught.exception), "planning_driver_resume_boundary_mismatch")

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
