# Claude Code and Codex interactive-session capabilities

Research for [Research claude-code and codex interactive-session capabilities](https://github.com/earledotpy/axiom-forge/issues/94), checked 2026-07-19. Sources are first-party documentation unless marked as local repository context.

## Scope and local constraint

ADR 0011 defines a planning session as an interactive CLI-agent session hosted by the workbench. It may read the target repository and Forge evidence and run non-mutating investigation commands in a disposable worktree, but it must change nothing durable. Its only durable outputs are a Forge-owned transcript and a zero-authority draft proposal. The session is a planning surface, not the execution or promotion path. See [ADR 0011](adr/0011-planning-session-boundary.md) and the canonical terms in [CONTEXT.md](../CONTEXT.md).

The vendor documentation below demonstrates useful controls and transport shapes. It does not transfer the Forge trust boundary to either vendor.

## Findings

| Capability | Claude Code | Codex CLI | Contract implication |
| --- | --- | --- | --- |
| Programmatic conversation | The CLI has print mode (`claude -p`), stdin input, `--input-format stream-json`, and the Agent SDK exposes an async `query()` stream. The SDK supports queued multi-turn streaming input. ([CLI reference](https://docs.anthropic.com/en/docs/claude-code/cli-usage), [streaming input](https://code.claude.com/docs/en/agent-sdk/streaming-vs-single-mode), [Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview)) | `codex exec` runs non-interactively and streams formatted output or JSONL. `codex app-server` provides a JSONL-over-stdio, WebSocket, or Unix-socket protocol for rich clients, with thread/turn/item events. ([CLI reference](https://developers.openai.com/codex/cli/reference/), [app server](https://developers.openai.com/codex/app-server)) | An adapter must expose a server-drivable bidirectional session: start, send a user turn, receive incremental events, detect completion/failure, and shut down. A one-shot prompt wrapper is insufficient for the planning-session surface. |
| Resume and branch | `--resume`/`-r`, `--continue`, and `--fork-session` are documented. The SDK returns a session ID and accepts `resume`. ([CLI reference](https://docs.anthropic.com/en/docs/claude-code/cli-usage), [Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview)) | `codex resume` and `codex exec resume` continue sessions by ID or most recent session; `codex fork` creates a new chat while preserving the original transcript. App-server exposes `thread/resume` and `thread/fork`. ([CLI reference](https://developers.openai.com/codex/cli/reference/), [non-interactive mode](https://developers.openai.com/codex/non-interactive-mode), [app server](https://developers.openai.com/codex/app-server)) | The adapter contract must carry an opaque session identifier, support resume, and declare whether fork is supported. Resumption must not silently change the worktree, policy, or transcript identity. |
| Machine-readable stream | CLI print mode supports `json` and `stream-json`; stream output contains typed session messages and can include partial messages. The Agent SDK can yield raw stream events, complete messages, tool calls, and a final result. ([CLI reference](https://docs.anthropic.com/en/docs/claude-code/cli-usage), [streaming output](https://code.claude.com/docs/en/agent-sdk/streaming-output)) | `codex exec --json` emits JSON Lines events such as thread, turn, item, and error events. App-server emits lifecycle and incremental `turn/*` and `item/*` notifications. ([non-interactive mode](https://developers.openai.com/codex/non-interactive-mode), [app server](https://developers.openai.com/codex/app-server)) | The adapter must preserve the raw event stream, including input, output, tool calls, approvals, errors, and termination metadata. A rendered UI transcript alone is not evidence. |
| Transcript persistence | The Agent SDK documents local JSONL transcripts under `~/.claude/projects/` and a `SessionStore` interface that mirrors entries to an application-controlled backend. This provides a path to capture and resume transcripts, but the default location is vendor-owned local state. ([session storage](https://code.claude.com/docs/en/agent-sdk/session-storage)) | Codex app-server documents persisted JSONL thread logs, thread read/list/archive/resume operations, and streamed events. `codex exec --json` also lets a host capture every emitted event. ([app server](https://developers.openai.com/codex/app-server), [non-interactive mode](https://developers.openai.com/codex/non-interactive-mode)) | Forge must copy or record the complete session stream into a Forge-owned transcript artifact with adapter version, session ID, working-directory identity, policy, timestamps, exit status, and hashes. Vendor session files may support resume but are not sufficient as Forge evidence by themselves. |
| Working-directory and tool controls | The CLI supports `--add-dir`, permission modes, `--allowedTools`, `--disallowedTools`, and debug-file/log options. The Agent SDK supports `tools`, allowed/disallowed tools, permission callbacks, and hooks. A read-only example allows `Read`, `Glob`, and `Grep`. ([CLI reference](https://docs.anthropic.com/en/docs/claude-code/cli-usage), [Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview), [custom tools and access](https://code.claude.com/docs/en/agent-sdk/custom-tools)) | The CLI supports `--cd`, `--sandbox read-only|workspace-write|danger-full-access`, approval policies, `--add-dir`, and permission profiles. The app-server thread-start shape carries `cwd`, approval policy, and sandbox settings. ([CLI reference](https://developers.openai.com/codex/cli/reference/), [app server](https://developers.openai.com/codex/app-server)) | Vendor controls are useful configuration inputs, not the security boundary. Forge must launch in a disposable worktree, pass an explicit policy, constrain tools to the approved investigation set, and independently verify that no durable state changed. No adapter may claim planning safety merely because it has a “plan”, “read-only”, or sandbox flag. |
| Structured draft handoff | The Agent SDK supports validated JSON Schema output via `outputFormat`/`output_format`, returned as `structured_output` after multi-turn tool use. The CLI reference separately exposes JSON and stream-JSON output. ([structured outputs](https://code.claude.com/docs/en/agent-sdk/structured-outputs)) | `codex exec` supports `--output-schema` for a JSON Schema-conforming final response and `-o` for writing the final message; JSONL remains available for progress and provenance. ([non-interactive mode](https://developers.openai.com/codex/non-interactive-mode)) | The adapter must produce a schema-validated, zero-authority proposal with at least task text, target scope, acceptance check, and suggested adapter. The workbench must treat it as editable input and never as delegation approval. |
| Approval and user interaction | The Agent SDK exposes a `canUseTool` callback for approval and questions, and hooks can apply controls before the permission flow. | App-server exposes approval requests for command execution, file changes, and tool calls; clients must answer them. The documented `thread/shellCommand` path runs outside the thread sandbox and is explicitly for user-initiated commands. ([user input and approvals](https://code.claude.com/docs/en/agent-sdk/user-input), [app server](https://developers.openai.com/codex/app-server)) | The adapter contract must make approval events explicit and auditable. The workbench must not expose an unreviewed “shell command” escape hatch, and planning-session approvals must not become execution or promotion authority. |

## Capability-contract sketch

An adapter may host a planning session only if it can satisfy all mandatory requirements below. The contract is vendor-neutral; CLI-specific flags and protocols stay inside the adapter.

### Session lifecycle

1. `start(request) -> session`: launch from the operator-selected disposable worktree with an opaque session ID, adapter/version identity, effective policy, and working-directory identity recorded before the first turn.
2. `send(session, user_message)`: deliver a user turn without requiring a new process for every turn, or document a functionally equivalent transport.
3. `events(session) -> ordered stream`: emit loss-detectable, machine-readable events for user messages, assistant messages, reasoning/tool activity as exposed by the vendor, approvals, tool results, errors, and terminal status.
4. `resume(session_id, worktree_identity, policy_identity)`: continue only when the worktree and policy match the recorded session; otherwise fail closed or start a new session.
5. `close(session) -> receipt`: report exit status, final event sequence, transcript hash, and any detected boundary violation.

### Safety and confinement

- The host, not the adapter, owns creation and disposal of the worktree.
- The adapter must accept an explicit working directory and an explicit permission/tool policy.
- The session must be able to run with all durable writes blocked outside the disposable worktree and all mutating tools disabled or denied for planning.
- The host must capture and audit every approval request, tool invocation, tool result, filesystem/process side effect, and policy-denial event that the transport exposes.
- A vendor “dangerous bypass”, broad full-access mode, or unreviewed shell path is never acceptable for a planning session.
- The adapter must report unsupported controls as unsupported. It must not silently substitute a weaker mode.

### Transcript and proposal

- The Forge-owned transcript is an append-only, replayable record of the ordered input/output event stream plus adapter provenance and receipt metadata. Vendor-local session storage is an optional resume mechanism, not the canonical artifact.
- Transcript capture must fail closed on malformed or missing events when the adapter claims a structured transport.
- The proposal output must validate against the Forge draft-proposal schema and include `task_text`, `target_scope`, `acceptance_check`, and `suggested_adapter` (with provenance pointing to the session transcript).
- The proposal has no authority: only the operator can edit, approve, and convert it into delegation artifacts. The adapter cannot create a task, approve a task, delegate execution, promote a patch, or modify the main repository.

### Capability declaration

Each adapter should publish a machine-readable declaration with booleans or explicit modes for:

```text
interactive_transport: required
streamed_input: required
streamed_output: required
resume: required
fork: optional
structured_proposal: required
transcript_capture: required
explicit_working_directory: required
non_mutating_policy: required
tool_allowlist_or_denylist: required
host_enforced_confinement: required
approval_event_capture: required
```

“Required” means the adapter cannot host a Stage 1 planning session without it. “Optional” means the workbench can omit the feature while preserving the core contract. A claim is not sufficient: the adapter qualification or feasibility probe must demonstrate the declared behavior in the actual installed CLI configuration.

## Decision

Both Claude Code and Codex CLI are technically capable of hosting the Stage 1 planning-session shape. Codex offers a particularly direct app-server protocol for a server-hosted session and a CLI JSONL path for non-interactive automation. Claude Code offers both CLI stream-JSON and an Agent SDK with resumable async sessions, externally mirrored JSONL transcripts, tool controls, and schema-validated output.

Neither vendor should be treated as satisfying the Forge contract merely from documentation. The first implementation should use each vendor’s strongest structured transport, capture the raw stream into Forge-owned evidence, and enforce the disposable-worktree/non-mutating boundary outside the vendor process. The seven free-tier adapters should be evaluated against the same declaration and evidence requirements rather than granted a weaker contract.

## Sources

- [Anthropic Claude Code CLI reference](https://docs.anthropic.com/en/docs/claude-code/cli-usage)
- [Claude Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview)
- [Claude Agent SDK streaming input](https://code.claude.com/docs/en/agent-sdk/streaming-vs-single-mode)
- [Claude Agent SDK streaming output](https://code.claude.com/docs/en/agent-sdk/streaming-output)
- [Claude Agent SDK session storage](https://code.claude.com/docs/en/agent-sdk/session-storage)
- [Claude Agent SDK structured outputs](https://code.claude.com/docs/en/agent-sdk/structured-outputs)
- [Claude Agent SDK approvals and user input](https://code.claude.com/docs/en/agent-sdk/user-input)
- [Claude Agent SDK custom tools and access controls](https://code.claude.com/docs/en/agent-sdk/custom-tools)
- [OpenAI Codex CLI reference](https://developers.openai.com/codex/cli/reference/)
- [OpenAI Codex non-interactive mode](https://developers.openai.com/codex/non-interactive-mode)
- [OpenAI Codex app-server](https://developers.openai.com/codex/app-server)
- [Axiom Forge ADR 0011](adr/0011-planning-session-boundary.md)

