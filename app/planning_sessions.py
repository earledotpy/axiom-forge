from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class PlanningSessionError(ValueError):
    pass


_TERMINAL_STATES = {"CLOSED", "FAILED", "BOUNDARY_VIOLATION"}
_SESSION_STATES = {"ACTIVE", "IDLE", *_TERMINAL_STATES}
_REQUIRED_DRIVER_METHODS = ("start", "send", "close")
_FIXED_POLICY = {
    "name": "investigation-only-v1",
    "allow": ["read_target_repository", "read_forge_evidence", "non_mutating_investigation"],
    "deny": ["writes", "credential_environment_commands", "secret_paths", "tool_approval_changes"],
}


class PlanningSessionStore:
    """Forge-owned planning-session lifecycle and local evidence store.

    Drivers are injected at the server boundary. They receive a fixed policy and
    worktree, but never a Forge approval or delegation capability.
    """

    def __init__(self, forge_root: Path, drivers: dict[str, Any]):
        self.root = forge_root.resolve()
        self.sessions_root = self.root / "sessions"
        self.drivers = dict(drivers)
        self._validate_drivers()
        self._recover_interrupted_sessions()

    def start(self, payload: object) -> dict[str, Any]:
        request = _start_request(payload)
        driver = self.drivers.get(request["adapter"])
        if driver is None:
            raise PlanningSessionError("planning_driver_unavailable")
        target = _target_repository(request["target_repo"], self.root)
        base_sha = _git(target, "rev-parse", "HEAD")
        session_id = uuid.uuid4().hex
        session_dir = self.sessions_root / session_id
        worktree = session_dir / "worktree"
        session_dir.mkdir(parents=True, exist_ok=False)
        _git(target, "worktree", "add", "--detach", str(worktree), base_sha)
        metadata = {
            "authority": "planning_session",
            "session_id": session_id,
            "adapter": request["adapter"],
            "adapter_identity": request["adapter"],
            "target_repo": str(target),
            "planning_snapshot_sha": base_sha,
            "worktree": str(worktree),
            "policy": _FIXED_POLICY,
            "policy_identity": _json_hash(_FIXED_POLICY),
            "state": "ACTIVE",
            "resume_identity": None,
            "created_at": _now(),
            "source": _source_snapshot(request),
        }
        self._write_metadata(session_dir, metadata)
        self._append(session_dir, {"type": "operator_prompt", "text": request["prompt"], "at": _now()})
        try:
            result = driver.start(
                session_id=session_id,
                worktree=worktree,
                policy=_FIXED_POLICY.copy(),
                seed=metadata["source"],
            )
            self._consume_driver_result(session_dir, metadata, result)
            self._enforce_baseline(session_dir, metadata)
        except Exception as error:
            if isinstance(error, PlanningSessionError):
                raise
            self._terminal(session_dir, metadata, "FAILED", "planning_driver_start_failed")
            raise PlanningSessionError("planning_driver_start_failed") from error
        return self.session(session_id)

    def send(self, session_id: str, message: object) -> dict[str, Any]:
        session_dir, metadata = self._load_active(session_id)
        if not isinstance(message, str) or not message.strip():
            if isinstance(message, dict) and "tool_approval" in message:
                self._append(session_dir, {"type": "policy_denied", "reason": "planning_policy_change_forbidden", "at": _now()})
                raise PlanningSessionError("planning_policy_change_forbidden")
            raise PlanningSessionError("invalid_planning_message")
        driver = self.drivers[metadata["adapter"]]
        metadata["state"] = "ACTIVE"
        self._write_metadata(session_dir, metadata)
        self._append(session_dir, {"type": "operator_message", "text": message, "at": _now()})
        try:
            result = driver.send(
                resume_identity=metadata["resume_identity"], message=message, policy=_FIXED_POLICY.copy()
            )
            self._consume_driver_result(session_dir, metadata, result)
            self._enforce_baseline(session_dir, metadata)
        except PlanningSessionError:
            raise
        except Exception as error:
            self._terminal(session_dir, metadata, "FAILED", "planning_driver_lost")
            raise PlanningSessionError("planning_driver_lost") from error
        return self.session(session_id)

    def close(self, session_id: str) -> dict[str, Any]:
        session_dir, metadata = self._load(session_id)
        if metadata["state"] in _TERMINAL_STATES:
            return self.session(session_id)
        try:
            self.drivers[metadata["adapter"]].close(resume_identity=metadata["resume_identity"])
        except Exception:
            self._terminal(session_dir, metadata, "FAILED", "planning_driver_close_failed")
        else:
            self._enforce_baseline(session_dir, metadata)
            if metadata["state"] not in _TERMINAL_STATES:
                self._terminal(session_dir, metadata, "CLOSED", None)
        return self.session(session_id)

    def session(self, session_id: str) -> dict[str, Any]:
        _, metadata = self._load(session_id)
        return dict(metadata)

    def list_sessions(self) -> list[dict[str, Any]]:
        if not self.sessions_root.exists():
            return []
        return [self.session(path.name) for path in sorted(self.sessions_root.iterdir(), reverse=True) if path.is_dir()]

    def proposal_for_approval(self, session_id: str, version: object) -> dict[str, Any]:
        session_dir, metadata = self._load(session_id)
        if metadata["state"] == "BOUNDARY_VIOLATION":
            raise PlanningSessionError("planning_session_not_eligible_for_approval")
        if not isinstance(version, int) or version < 1:
            raise PlanningSessionError("invalid_planning_proposal_reference")
        path = session_dir / "proposals" / f"{version:04d}.json"
        try:
            proposal = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise PlanningSessionError("planning_proposal_not_found") from error
        if not proposal.get("valid"):
            raise PlanningSessionError("planning_proposal_invalid")
        return {"authority": "draft_only", "session_id": session_id, "proposal_version": version, **proposal["proposal"]}

    def _consume_driver_result(self, session_dir: Path, metadata: dict[str, Any], result: object) -> None:
        if not isinstance(result, dict) or not isinstance(result.get("events"), list):
            raise PlanningSessionError("planning_driver_contract_violation")
        resume_identity = result.get("resume_identity")
        if not isinstance(resume_identity, str) or not resume_identity:
            raise PlanningSessionError("planning_driver_contract_violation")
        metadata["resume_identity"] = resume_identity
        sequence = 0
        for event in result["events"]:
            if not isinstance(event, dict) or event.get("sequence") != sequence + 1 or not isinstance(event.get("type"), str):
                raise PlanningSessionError("planning_event_stream_invalid")
            sequence += 1
            if event["type"] == "secret_exposure":
                self._append(session_dir, {"type": "secret_exposure", "text": "[redacted]", "at": _now()})
                self._terminal(session_dir, metadata, "FAILED", "planning_secret_exposure")
                return
            if event["type"] == "proposal":
                self._record_proposal(session_dir, event.get("proposal"))
            self._append(session_dir, _redacted_event(event))
            if event["type"] == "idle":
                metadata["state"] = "IDLE"
        self._write_metadata(session_dir, metadata)

    def _record_proposal(self, session_dir: Path, proposal: object) -> None:
        proposals = session_dir / "proposals"
        proposals.mkdir(exist_ok=True)
        version = len(list(proposals.glob("*.json"))) + 1
        validated = _validate_proposal(proposal, set(self.drivers))
        (proposals / f"{version:04d}.json").write_text(json.dumps(validated, indent=2) + "\n", encoding="utf-8")

    def _enforce_baseline(self, session_dir: Path, metadata: dict[str, Any]) -> None:
        worktree = Path(metadata["worktree"])
        try:
            changed = _git(worktree, "status", "--porcelain=v1", "--untracked-files=all")
            head = _git(worktree, "rev-parse", "HEAD")
        except PlanningSessionError:
            self._terminal(session_dir, metadata, "FAILED", "planning_worktree_unavailable")
            return
        if changed or head != metadata["planning_snapshot_sha"]:
            self._terminal(session_dir, metadata, "BOUNDARY_VIOLATION", "planning_worktree_changed")

    def _terminal(self, session_dir: Path, metadata: dict[str, Any], state: str, reason: str | None) -> None:
        metadata["state"] = state
        metadata["terminal_reason"] = reason
        metadata["closed_at"] = _now()
        self._write_metadata(session_dir, metadata)
        transcript = session_dir / "transcript.jsonl"
        receipt = {
            "session_id": metadata["session_id"], "terminal_status": state, "reason": reason,
            "transcript_sha256": _file_hash(transcript), "adapter_identity": metadata["adapter_identity"],
            "resume_identity": metadata["resume_identity"], "planning_snapshot_sha": metadata["planning_snapshot_sha"],
            "policy_identity": metadata["policy_identity"], "closed_at": metadata["closed_at"],
        }
        (session_dir / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        worktree = Path(metadata["worktree"])
        if worktree.exists():
            subprocess.run(["git", "-C", metadata["target_repo"], "worktree", "remove", "--force", str(worktree)], capture_output=True, text=True)
            shutil.rmtree(worktree, ignore_errors=True)

    def _load(self, session_id: str) -> tuple[Path, dict[str, Any]]:
        if not isinstance(session_id, str) or not session_id or "/" in session_id or "\\" in session_id:
            raise PlanningSessionError("invalid_planning_session_reference")
        session_dir = self.sessions_root / session_id
        try:
            metadata = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise PlanningSessionError("planning_session_not_found") from error
        if not isinstance(metadata, dict) or metadata.get("session_id") != session_id or metadata.get("state") not in _SESSION_STATES:
            raise PlanningSessionError("planning_session_not_found")
        return session_dir, metadata

    def _load_active(self, session_id: str) -> tuple[Path, dict[str, Any]]:
        session_dir, metadata = self._load(session_id)
        if metadata["state"] != "IDLE":
            raise PlanningSessionError("planning_session_not_resumable")
        return session_dir, metadata

    def _append(self, session_dir: Path, event: dict[str, Any]) -> None:
        with (session_dir / "transcript.jsonl").open("a", encoding="utf-8") as transcript:
            transcript.write(json.dumps(event, sort_keys=True) + "\n")

    def _write_metadata(self, session_dir: Path, metadata: dict[str, Any]) -> None:
        (session_dir / "session.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    def _validate_drivers(self) -> None:
        for driver in self.drivers.values():
            if any(not callable(getattr(driver, method, None)) for method in _REQUIRED_DRIVER_METHODS):
                raise PlanningSessionError("planning_driver_contract_violation")

    def _recover_interrupted_sessions(self) -> None:
        if not self.sessions_root.exists():
            return
        for path in self.sessions_root.iterdir():
            if not path.is_dir():
                continue
            try:
                _, metadata = self._load(path.name)
            except PlanningSessionError:
                continue
            if metadata["state"] == "ACTIVE":
                self._terminal(path, metadata, "FAILED", "planning_server_restarted")


def _start_request(payload: object) -> dict[str, str]:
    if not isinstance(payload, dict) or set(payload) - {"adapter", "target_repo", "prompt", "issue_seed"}:
        raise PlanningSessionError("invalid_planning_session_request")
    values = {key: payload.get(key) for key in ("adapter", "target_repo", "prompt")}
    if any(not isinstance(value, str) or not value.strip() for value in values.values()):
        raise PlanningSessionError("invalid_planning_session_request")
    return values


def _source_snapshot(request: dict[str, str]) -> dict[str, Any]:
    return {"kind": "free_form", "prompt_sha256": _json_hash(request["prompt"]), "captured_at": _now()}


def _target_repository(raw_path: str, forge_root: Path) -> Path:
    target = Path(raw_path).expanduser().resolve()
    if target == forge_root or forge_root in target.parents or not target.is_dir():
        raise PlanningSessionError("planning_target_repository_invalid")
    if Path(_git(target, "rev-parse", "--show-toplevel")).resolve() != target:
        raise PlanningSessionError("planning_target_repository_invalid")
    if _git(target, "status", "--porcelain"):
        raise PlanningSessionError("planning_target_repository_dirty")
    return target


def _git(path: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise PlanningSessionError("planning_git_operation_failed")
    return result.stdout.strip()


def _validate_proposal(proposal: object, adapters: set[str]) -> dict[str, Any]:
    if not isinstance(proposal, dict):
        return {"valid": False, "reason": "proposal_not_an_object", "proposal": proposal}
    keys = {"task_text", "target_scope", "acceptance_check", "suggested_adapter"}
    if set(proposal) != keys or not all(isinstance(proposal[key], str) and proposal[key].strip() for key in keys - {"target_scope"}):
        return {"valid": False, "reason": "proposal_schema_invalid", "proposal": proposal}
    scope = proposal["target_scope"]
    if not isinstance(scope, list) or not scope or any(not isinstance(path, str) or not path or path.startswith("/") or ".." in Path(path).parts for path in scope):
        return {"valid": False, "reason": "proposal_scope_invalid", "proposal": proposal}
    if proposal["suggested_adapter"] not in adapters:
        return {"valid": False, "reason": "proposal_adapter_invalid", "proposal": proposal}
    return {"valid": True, "proposal": proposal}


def _redacted_event(event: dict[str, Any]) -> dict[str, Any]:
    event = dict(event)
    if "secret" in event:
        event["secret"] = "[redacted]"
    return event


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _json_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
