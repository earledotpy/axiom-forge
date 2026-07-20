from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Callable


REQUIRED_PLANNING_CAPABILITIES = (
    "interactive_transport",
    "streamed_input",
    "streamed_output",
    "resume",
    "structured_proposal",
    "transcript_capture",
    "explicit_working_directory",
    "non_mutating_policy",
    "tool_allowlist_or_denylist",
    "host_enforced_confinement",
    "approval_event_capture",
)

_PROPOSAL_KEYS = {"task_text", "target_scope", "acceptance_check", "suggested_adapter"}
_SAFE_ENVIRONMENT_NAMES = {
    "APPDATA", "COMSPEC", "HOMEDRIVE", "HOMEPATH", "LOCALAPPDATA", "PATH",
    "PATHEXT", "SYSTEMDRIVE", "SYSTEMROOT", "TEMP", "TMP", "USERPROFILE",
}
Runner = Callable[..., subprocess.CompletedProcess[str]]


def fixed_policy_identity(policy: object) -> str:
    encoded = json.dumps(policy, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def planning_driver_registry(runner: Runner | None = None) -> dict[str, object]:
    return {
        "codex": CodexPlanningDriver(runner=runner),
        "claude-code": ClaudePlanningDriver(runner=runner),
    }


class _CliPlanningDriver:
    capabilities = {name: True for name in REQUIRED_PLANNING_CAPABILITIES}
    capabilities["host_enforced_confinement"] = False
    executable = ""
    adapter_name = ""

    def __init__(self, runner: Runner | None = None):
        self._runner = runner or _run
        self._identity: str | None = None
        self._sessions: dict[str, tuple[Path, str]] = {}

    def identity(self) -> str:
        if self._identity is None:
            result = self._runner(
                [self.executable, "--version"],
                cwd=Path.cwd(),
                env=_planning_environment(),
            )
            if result.returncode != 0 or not result.stdout.strip():
                raise RuntimeError("planning_driver_identity_unavailable")
            self._identity = result.stdout.strip().splitlines()[0]
        return self._identity

    def start(self, *, session_id, worktree, policy, seed, prompt, resume_identity=None):
        del session_id, resume_identity
        self.identity()
        result = self._run_turn(Path(worktree), _planning_prompt(seed, prompt), None)
        self._sessions[result["resume_identity"]] = (Path(worktree).resolve(), fixed_policy_identity(policy))
        return result

    def resume(self, *, resume_identity, worktree, policy):
        expected = self._sessions.get(resume_identity)
        actual = (Path(worktree).resolve(), fixed_policy_identity(policy))
        if expected != actual:
            raise RuntimeError("planning_driver_resume_boundary_mismatch")
        return resume_identity

    def send(self, *, resume_identity, message, policy):
        session = self._sessions.get(resume_identity)
        if session is None or session[1] != fixed_policy_identity(policy):
            raise RuntimeError("planning_driver_resume_boundary_mismatch")
        result = self._run_turn(session[0], message, resume_identity)
        if result["resume_identity"] != resume_identity:
            raise RuntimeError("planning_driver_resume_identity_changed")
        return result

    def events(self, result):
        events = result.get("events") if isinstance(result, dict) else None
        if not isinstance(events, list):
            raise RuntimeError("planning_driver_event_stream_unavailable")
        return events

    def close(self, *, resume_identity):
        self._sessions.pop(resume_identity, None)
        return {"resume_identity": resume_identity, "closed": True}

    def _run_turn(self, worktree: Path, prompt: str, resume_identity: str | None) -> dict:
        result = self._runner(
            self._command(worktree, prompt, resume_identity),
            cwd=worktree,
            env=_planning_environment(),
        )
        if result.returncode != 0:
            raise RuntimeError(f"{self.adapter_name}_planning_turn_failed")
        records = _json_lines(result.stdout)
        return _normalize_events(self.adapter_name, records, resume_identity)

    def _command(self, worktree: Path, prompt: str, resume_identity: str | None) -> list[str]:
        raise NotImplementedError


class CodexPlanningDriver(_CliPlanningDriver):
    executable = "codex"
    adapter_name = "codex"

    def _command(self, worktree: Path, prompt: str, resume_identity: str | None) -> list[str]:
        if resume_identity is None:
            return [
                self.executable, "exec", "--json", "--sandbox", "read-only",
                "-c", 'approval_policy="never"', "--cd", str(worktree), prompt,
            ]
        return [
            self.executable, "exec", "resume", "--json",
            "-c", 'sandbox_mode="read-only"',
            "-c", 'approval_policy="never"', resume_identity, prompt,
        ]


class ClaudePlanningDriver(_CliPlanningDriver):
    executable = "claude"
    adapter_name = "claude-code"

    def _command(self, worktree: Path, prompt: str, resume_identity: str | None) -> list[str]:
        command = [
            self.executable, "-p", "--output-format", "stream-json", "--verbose",
            "--permission-mode", "plan", "--allowedTools",
            "Read,Glob,Grep,Bash(git status *),Bash(git log *),Bash(git diff *),Bash(git show *),Bash(git grep *),Bash(rg *)",
            "--disable-slash-commands", "--strict-mcp-config", "--mcp-config",
            '{"mcpServers":{}}',
        ]
        if resume_identity is not None:
            command.extend(["--resume", resume_identity])
        command.append(prompt)
        return command


def _run(command: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, check=False)


def _planning_environment() -> dict[str, str]:
    return {name: value for name, value in os.environ.items() if name.upper() in _SAFE_ENVIRONMENT_NAMES}


def _planning_prompt(seed: object, prompt: str) -> str:
    return "\n".join([
        "You are in an Axiom Forge planning session. Investigate only.",
        "Do not edit files, change Git state, request permissions, expose secrets, delegate execution, or approve work.",
        "When you have a bounded proposal, emit one JSON object with exactly task_text, target_scope, acceptance_check, and suggested_adapter.",
        f"Planning source: {json.dumps(seed, sort_keys=True)}",
        f"Operator: {prompt}",
    ])


def _json_lines(output: str) -> list[dict]:
    records = []
    for line in output.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise RuntimeError("planning_driver_event_stream_invalid") from error
        if not isinstance(record, dict):
            raise RuntimeError("planning_driver_event_stream_invalid")
        records.append(record)
    if not records:
        raise RuntimeError("planning_driver_event_stream_invalid")
    return records


def _normalize_events(adapter: str, records: list[dict], expected_resume_identity: str | None) -> dict:
    resume_identity = expected_resume_identity
    events = []
    for record in records:
        discovered = _resume_identity(adapter, record)
        if discovered:
            resume_identity = discovered
        text = _assistant_text(adapter, record)
        event_type = _event_type(record, text)
        event = {"sequence": len(events) + 1, "type": event_type, "vendor_event": record}
        if text:
            event["text"] = text
        events.append(event)
        proposal = _proposal_from_text(text)
        if proposal is not None:
            events.append({"sequence": len(events) + 1, "type": "proposal", "proposal": proposal})
    if not resume_identity:
        raise RuntimeError("planning_driver_resume_identity_missing")
    events.append({"sequence": len(events) + 1, "type": "idle"})
    return {"resume_identity": resume_identity, "events": events}


def _resume_identity(adapter: str, record: dict) -> str | None:
    if adapter == "codex" and record.get("type") == "thread.started":
        value = record.get("thread_id")
    elif adapter == "claude-code":
        value = record.get("session_id")
    else:
        value = None
    return value if isinstance(value, str) and value else None


def _assistant_text(adapter: str, record: dict) -> str | None:
    if adapter == "codex" and record.get("type") == "item.completed":
        item = record.get("item")
        if isinstance(item, dict) and item.get("type") == "agent_message":
            text = item.get("text")
            return text if isinstance(text, str) else None
    if adapter == "claude-code" and record.get("type") == "assistant":
        message = record.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, list):
            parts = [
                part.get("text")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str)
            ]
            return "\n".join(parts) if parts else None
    return None


def _event_type(record: dict, text: str | None) -> str:
    if text is not None:
        return "message"
    record_type = str(record.get("type") or "")
    lowered = record_type.casefold()
    if "approval" in lowered or "permission" in lowered:
        return "approval"
    if "tool" in lowered or "command" in lowered or "file_change" in lowered:
        return "tool"
    if "error" in lowered or record.get("is_error") is True:
        return "error"
    return "driver_event"


def _proposal_from_text(text: str | None) -> dict | None:
    if not text:
        return None
    candidate = text.strip()
    fence = chr(96) * 3
    if candidate.startswith(fence) and candidate.endswith(fence):
        lines = candidate.splitlines()
        candidate = "\n".join(lines[1:-1]).strip()
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) and set(value) == _PROPOSAL_KEYS else None
