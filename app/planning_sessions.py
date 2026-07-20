from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock, Thread, current_thread
from typing import Any

from app.planning_drivers import REQUIRED_PLANNING_CAPABILITIES


class PlanningSessionError(ValueError):
    pass


_TERMINAL_STATES = {"CLOSED", "FAILED", "BOUNDARY_VIOLATION"}
_SESSION_STATES = {"ACTIVE", "IDLE", *_TERMINAL_STATES}
_REQUIRED_DRIVER_METHODS = ("identity", "start", "send", "events", "resume", "close")
_STORE_ENFORCED_CAPABILITIES = {"host_enforced_confinement"}
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

    def __init__(
        self,
        forge_root: Path,
        drivers: dict[str, Any],
        *,
        secret_values: list[str] | None = None,
    ):
        self.root = forge_root.resolve()
        self.sessions_root = self.root / "sessions"
        self.drivers = dict(drivers)
        values = secret_values if secret_values is not None else _environment_secret_values()
        self.secret_values = tuple(
            sorted(
                {value for value in values if isinstance(value, str) and len(value) >= 6},
                key=len,
                reverse=True,
            )
        )
        self._turn_lock = Lock()
        self._turns = {}
        self._closing_sessions = set()
        self._validate_drivers()
        self._recover_interrupted_sessions()

    def start(self, payload: object) -> dict[str, Any]:
        request = _start_request(payload)
        driver = self.drivers.get(request["adapter"])
        if driver is None:
            raise PlanningSessionError("planning_driver_unavailable")
        target = _target_repository(request["target_repo"], self.root)
        source = _source_snapshot(request)
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
            "worktree_baseline": _git_state(worktree),
            "worktree": str(worktree),
            "policy": _FIXED_POLICY,
            "policy_identity": _json_hash(_FIXED_POLICY),
            "state": "ACTIVE",
            "resume_identity": None,
            "created_at": _now(),
            "source": source,
        }
        (session_dir / "source.json").write_text(
            json.dumps(metadata["source"], indent=2) + "\n", encoding="utf-8"
        )
        self._write_metadata(session_dir, metadata)
        self._append(session_dir, {"type": "operator_prompt", "text": self._scrub(request["prompt"]), "at": _now()})
        try:
            metadata["adapter_identity"] = _driver_identity(driver)
            self._write_metadata(session_dir, metadata)
            if getattr(driver, "background_turns", False):
                self._launch_turn(
                    driver,
                    session_dir,
                    metadata,
                    lambda event_sink: driver.start(
                        session_id=session_id, worktree=worktree, policy=_FIXED_POLICY.copy(),
                        seed=metadata["source"], prompt=request["prompt"], event_sink=event_sink,
                    ),
                    "planning_driver_start_failed",
                )
                return self.session(session_id)
            result = driver.start(
                session_id=session_id,
                worktree=worktree,
                policy=_FIXED_POLICY.copy(),
                seed=metadata["source"],
                prompt=request["prompt"],
            )
            self._consume_driver_result(driver, session_dir, metadata, result)
            if metadata["state"] not in _TERMINAL_STATES:
                self._enforce_baseline(session_dir, metadata)
        except PlanningSessionError:
            if metadata["state"] not in _TERMINAL_STATES:
                self._terminal(session_dir, metadata, "FAILED", "planning_driver_contract_violation")
            raise
        except Exception as error:
            self._terminal(session_dir, metadata, "FAILED", "planning_driver_start_failed")
            raise PlanningSessionError("planning_driver_start_failed") from error
        return self.session(session_id)

    def send(self, session_id: str, message: object) -> dict[str, Any]:
        session_dir, metadata = self._load_resumable(session_id)
        if not isinstance(message, str) or not message.strip():
            if isinstance(message, dict) and "tool_approval" in message:
                self._append(session_dir, {"type": "policy_denied", "reason": "planning_policy_change_forbidden", "at": _now()})
                raise PlanningSessionError("planning_policy_change_forbidden")
            raise PlanningSessionError("invalid_planning_message")
        driver = self.drivers[metadata["adapter"]]
        metadata["state"] = "ACTIVE"
        self._write_metadata(session_dir, metadata)
        self._append(session_dir, {"type": "operator_message", "text": self._scrub(message), "at": _now()})
        try:
            driver.resume(
                resume_identity=metadata["resume_identity"],
                worktree=Path(metadata["worktree"]),
                policy=_FIXED_POLICY.copy(),
            )
            if getattr(driver, "background_turns", False):
                self._launch_turn(
                    driver,
                    session_dir,
                    metadata,
                    lambda event_sink: driver.send(
                        resume_identity=metadata["resume_identity"], message=message,
                        policy=_FIXED_POLICY.copy(), event_sink=event_sink,
                    ), "planning_driver_lost",
                )
                return self.session(session_id)
            result = driver.send(
                resume_identity=metadata["resume_identity"], message=message, policy=_FIXED_POLICY.copy()
            )
            self._consume_driver_result(driver, session_dir, metadata, result)
            if metadata["state"] not in _TERMINAL_STATES:
                self._enforce_baseline(session_dir, metadata)
        except PlanningSessionError:
            if metadata["state"] not in _TERMINAL_STATES:
                self._terminal(session_dir, metadata, "FAILED", "planning_driver_contract_violation")
            raise
        except Exception as error:
            self._terminal(session_dir, metadata, "FAILED", "planning_driver_lost")
            raise PlanningSessionError("planning_driver_lost") from error
        return self.session(session_id)

    def close(self, session_id: str) -> dict[str, Any]:
        session_dir, metadata = self._load(session_id)
        if metadata["state"] in _TERMINAL_STATES:
            return self.session(session_id)
        driver = self.drivers[metadata["adapter"]]
        with self._turn_lock:
            self._closing_sessions.add(session_id)
            thread = self._turns.get(session_id)
        try:
            close_kwargs = {"resume_identity": metadata["resume_identity"]}
            if getattr(driver, "background_turns", False):
                close_kwargs["session_id"] = session_id
            driver.close(**close_kwargs)
            if thread is not None and thread is not current_thread():
                thread.join(timeout=6)
                if thread.is_alive():
                    raise RuntimeError("planning_driver_close_timed_out")
            _, metadata = self._load(session_id)
        except Exception:
            try:
                _, metadata = self._load(session_id)
            except PlanningSessionError:
                pass
            if metadata["state"] not in _TERMINAL_STATES:
                self._terminal(session_dir, metadata, "FAILED", "planning_driver_close_failed")
        else:
            self._enforce_baseline(session_dir, metadata)
            if metadata["state"] not in _TERMINAL_STATES:
                self._terminal(session_dir, metadata, "CLOSED", None)
        finally:
            with self._turn_lock:
                self._closing_sessions.discard(session_id)
        return self.session(session_id)

    def session(self, session_id: str) -> dict[str, Any]:
        session_dir, metadata = self._load(session_id)
        events = []
        transcript = session_dir / "transcript.jsonl"
        if transcript.is_file():
            for line in transcript.read_text(encoding="utf-8").splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict):
                    events.append(event)
        proposals = []
        proposals_dir = session_dir / "proposals"
        if proposals_dir.is_dir():
            for path in sorted(proposals_dir.glob("*.json")):
                try:
                    proposal = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                proposals.append({
                    "version": int(path.stem),
                    "proposal_sha256": _file_hash(path),
                    **proposal,
                })
        return {**metadata, "events": events, "proposals": proposals}

    def list_sessions(self) -> list[dict[str, Any]]:
        if not self.sessions_root.exists():
            return []
        return [self.session(path.name) for path in sorted(self.sessions_root.iterdir(), reverse=True) if path.is_dir()]

    def proposal_for_approval(self, session_id: str, version: object) -> dict[str, Any]:
        session_dir, metadata = self._load(session_id)
        if metadata["state"] not in {"IDLE", "CLOSED"}:
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
        return {
            "authority": "draft_only",
            "session_id": session_id,
            "proposal_version": version,
            "proposal_sha256": _file_hash(path),
            **proposal["proposal"],
        }

    def _launch_turn(self, driver, session_dir, metadata, turn, failure_reason):
        thread = Thread(
            target=self._finish_background_turn,
            args=(driver, session_dir, metadata, turn, failure_reason),
            daemon=True,
        )
        with self._turn_lock:
            self._turns[session_dir.name] = thread
        thread.start()

    def _finish_background_turn(self, driver, session_dir, metadata, turn, failure_reason):
        sequence = 0
        saw_idle = False

        def event_sink(event):
            nonlocal saw_idle, sequence
            sequence += 1
            self._consume_driver_event(session_dir, metadata, event, sequence)
            if event["type"] == "idle":
                saw_idle = True

        try:
            result = turn(event_sink)
            if not isinstance(result, dict):
                raise PlanningSessionError("planning_driver_contract_violation")
            try:
                events = driver.events(result)
            except Exception as error:
                raise PlanningSessionError("planning_driver_contract_violation") from error
            if events != []:
                raise PlanningSessionError("planning_driver_contract_violation")
            resume_identity = result.get("resume_identity")
            if not isinstance(resume_identity, str) or not resume_identity:
                raise PlanningSessionError("planning_driver_contract_violation")
            metadata["resume_identity"] = resume_identity
            if not saw_idle:
                raise PlanningSessionError("planning_event_stream_invalid")
            self._write_metadata(session_dir, metadata)
            if metadata["state"] not in _TERMINAL_STATES:
                self._enforce_baseline(session_dir, metadata)
            if metadata["state"] == "ACTIVE":
                metadata["state"] = "IDLE"
                self._write_metadata(session_dir, metadata)
        except PlanningSessionError:
            self._fail_background_turn(session_dir, failure_reason="planning_driver_contract_violation")
        except Exception:
            self._fail_background_turn(session_dir, failure_reason=failure_reason)
        finally:
            with self._turn_lock:
                if self._turns.get(session_dir.name) is current_thread():
                    self._turns.pop(session_dir.name, None)

    def _fail_background_turn(self, session_dir, failure_reason):
        with self._turn_lock:
            if session_dir.name in self._closing_sessions:
                return
        try:
            _, current = self._load(session_dir.name)
        except PlanningSessionError:
            return
        if current["state"] not in _TERMINAL_STATES:
            self._terminal(session_dir, current, "FAILED", failure_reason)

    def _consume_driver_event(self, session_dir, metadata, event, expected_sequence):
        if not isinstance(event, dict) or event.get("sequence") != expected_sequence or not isinstance(event.get("type"), str):
            raise PlanningSessionError("planning_event_stream_invalid")
        _, current = self._load(session_dir.name)
        if current["state"] in _TERMINAL_STATES:
            raise PlanningSessionError("planning_session_terminal")
        if event["type"] == "secret_exposure" or _contains_secret(event, self.secret_values):
            self._append(session_dir, {
                **_redacted_event(event, self.secret_values),
                "type": "secret_exposure",
                "text": "[redacted]",
                "at": _now(),
            })
            self._terminal(session_dir, metadata, "FAILED", "planning_secret_exposure")
            return False
        if event["type"] == "proposal":
            self._record_proposal(session_dir, event.get("proposal"))
        self._append(session_dir, _redacted_event(event, self.secret_values))
        return True

    def _consume_driver_result(self, driver: Any, session_dir: Path, metadata: dict[str, Any], result: object) -> None:
        if not isinstance(result, dict):
            raise PlanningSessionError("planning_driver_contract_violation")
        try:
            events = driver.events(result)
        except Exception as error:
            raise PlanningSessionError("planning_driver_contract_violation") from error
        if not isinstance(events, list):
            raise PlanningSessionError("planning_driver_contract_violation")
        resume_identity = result.get("resume_identity")
        if not isinstance(resume_identity, str) or not resume_identity:
            raise PlanningSessionError("planning_driver_contract_violation")
        metadata["resume_identity"] = resume_identity
        sequence = 0
        for event in events:
            sequence += 1
            if not self._consume_driver_event(session_dir, metadata, event, sequence):
                return
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
            current = _git_state(worktree)
        except PlanningSessionError:
            self._terminal(session_dir, metadata, "FAILED", "planning_worktree_unavailable")
            return
        if current != metadata["worktree_baseline"]:
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
            "worktree_baseline": metadata["worktree_baseline"], "created_at": metadata["created_at"],
            "source_sha256": _file_hash(session_dir / "source.json"),
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
        for attempt in range(5):
            try:
                metadata = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
            except PermissionError as error:
                if attempt == 4:
                    raise PlanningSessionError("planning_session_not_found") from error
                time.sleep(0.01)
            except (OSError, json.JSONDecodeError) as error:
                raise PlanningSessionError("planning_session_not_found") from error
            else:
                break
        if not isinstance(metadata, dict) or metadata.get("session_id") != session_id or metadata.get("state") not in _SESSION_STATES:
            raise PlanningSessionError("planning_session_not_found")
        return session_dir, metadata

    def _load_resumable(self, session_id: str) -> tuple[Path, dict[str, Any]]:
        session_dir, metadata = self._load(session_id)
        if metadata["state"] != "IDLE":
            raise PlanningSessionError("planning_session_not_resumable")
        return session_dir, metadata

    def _scrub(self, text: str) -> str:
        return _redacted_value(text, self.secret_values)

    def _append(self, session_dir: Path, event: dict[str, Any]) -> None:
        with (session_dir / "transcript.jsonl").open("a", encoding="utf-8") as transcript:
            transcript.write(json.dumps(event, sort_keys=True) + "\n")

    def _write_metadata(self, session_dir: Path, metadata: dict[str, Any]) -> None:
        temporary = session_dir / f".session-{uuid.uuid4().hex}.tmp"
        temporary.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, session_dir / "session.json")

    def _validate_drivers(self) -> None:
        for driver in self.drivers.values():
            capabilities = getattr(driver, "capabilities", None)
            if (
                any(not callable(getattr(driver, method, None)) for method in _REQUIRED_DRIVER_METHODS)
                or not isinstance(capabilities, dict)
                or any(
                    capabilities.get(name) is not True
                    for name in set(REQUIRED_PLANNING_CAPABILITIES) - _STORE_ENFORCED_CAPABILITIES
                )
            ):
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


def _start_request(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) - {"adapter", "target_repo", "prompt", "issue_seed"}:
        raise PlanningSessionError("invalid_planning_session_request")
    values = {key: payload.get(key) for key in ("adapter", "target_repo", "prompt")}
    if any(not isinstance(value, str) or not value.strip() for value in values.values()):
        raise PlanningSessionError("invalid_planning_session_request")
    issue_seed = payload.get("issue_seed")
    if issue_seed is not None and not isinstance(issue_seed, dict):
        raise PlanningSessionError("invalid_planning_issue_seed")
    return {**values, "issue_seed": issue_seed}


def _source_snapshot(request: dict[str, Any]) -> dict[str, Any]:
    issue = request.get("issue_seed")
    if issue is not None:
        required = {"number", "title", "body", "url"}
        if not required.issubset(issue) or not isinstance(issue.get("number"), int):
            raise PlanningSessionError("invalid_planning_issue_seed")
        body = issue.get("body")
        if not isinstance(body, str):
            raise PlanningSessionError("invalid_planning_issue_seed")
        return {
            "kind": "github_issue",
            "issue": issue,
            "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "captured_at": _now(),
        }
    return {"kind": "free_form", "prompt_sha256": _json_hash(request["prompt"]), "captured_at": _now()}


def _driver_identity(driver: Any) -> str:
    identity = getattr(driver, "identity", None)
    if not callable(identity):
        raise PlanningSessionError("planning_driver_contract_violation")
    value = identity()
    if not isinstance(value, str) or not value.strip():
        raise PlanningSessionError("planning_driver_contract_violation")
    return value


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


def _redacted_event(event: dict[str, Any], secret_values: tuple[str, ...]) -> dict[str, Any]:
    return _redacted_value(event, secret_values)


def _redacted_value(value: Any, secret_values: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        return {
            key: "[redacted]" if "secret" in str(key).casefold() else _redacted_value(item, secret_values)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redacted_value(item, secret_values) for item in value]
    if isinstance(value, str):
        for secret in secret_values:
            value = value.replace(secret, "[redacted]")
    return value


def _contains_secret(value: Any, secret_values: tuple[str, ...]) -> bool:
    if isinstance(value, dict):
        return any(_contains_secret(item, secret_values) for item in value.values())
    if isinstance(value, list):
        return any(_contains_secret(item, secret_values) for item in value)
    return isinstance(value, str) and any(secret in value for secret in secret_values)


def _environment_secret_values() -> list[str]:
    markers = ("TOKEN", "SECRET", "PASSWORD", "API_KEY")
    return [
        value
        for name, value in os.environ.items()
        if any(marker in name.upper() for marker in markers) and value
    ]


def _git_state(worktree: Path) -> dict[str, str]:
    symbolic = subprocess.run(
        ["git", "-C", str(worktree), "symbolic-ref", "-q", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "status": _git(worktree, "status", "--porcelain=v1", "--untracked-files=all"),
        "head": _git(worktree, "rev-parse", "HEAD"),
        "symbolic_head": symbolic.stdout.strip() if symbolic.returncode == 0 else "DETACHED",
        "local_refs": _git(worktree, "for-each-ref", "--format=%(refname):%(objectname)", "refs/heads"),
    }


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _json_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
