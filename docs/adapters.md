# Adapter Registry

This file records the known Axiom Forge agent adapters.

The adapter contract is:

```text
agents/<agent-name>.sh <task_file> <worktree>
````

The runner creates the worktree, calls the adapter, captures logs, captures the patch, and writes `record.json`.

Before and after invoking an adapter, the runner compares the target
checkout's Git status including ignored paths. A change fails the run with
`adapter_modified_outside_worktree`. This is checkout-mutation detection, not
an OS sandbox or a claim that arbitrary host-path writes are prevented.

Adapters are not trusted to promote code. Promotion is always handled by `scripts/promote.sh`.

## Status Levels

```text
stable        Granted standard trust through documented qualification or a grandfathered decision.
experimental  Has passed at least one local adapter experiment but has caveats.
blocked       Present or desired, but not currently adapter-compatible.
```

## Trust Levels

```text
test-only      Used only for harness tests.
standard       Suitable for normal local Axiom Forge runs.
experimental   Usable only as a cautious experiment.
```

## Registered Adapters

| Adapter                | Script                             | CLI dependency | Status       | Trust        | Notes                                                                                                                         |
| ---------------------- | ---------------------------------- | -------------- | ------------ | ------------ | ----------------------------------------------------------------------------------------------------------------------------- |
| manual-simulated-agent | `agents/manual-simulated-agent.sh` | Python         | stable       | standard     | Deterministic local adapter used for harness proof and debugging.                                                             |
| codex                  | `agents/codex.sh`                  | `codex`        | stable       | standard     | Proven with Codex CLI 0.137.0. Produces promoted gate branch.                                                                 |
| claude-code            | `agents/claude-code.sh`            | `claude`       | stable       | standard     | Proven with Claude Code 2.1.170. Produces promoted gate branch.                                                               |
| antigravity            | `agents/antigravity.sh`            | `agy`          | stable       | standard     | Qualified on `agy` 1.0.11 with model `Gemini 3.5 Flash (Low)`; see the evidence register. |
| copilot                | `agents/copilot.sh`                | `copilot`      | stable       | standard     | Qualified on GitHub Copilot CLI 1.0.64 with restricted `view,create,edit` tools; see the evidence register. |
| opencode               | `agents/opencode.sh`               | `opencode`     | stable       | standard     | Qualified on OpenCode 1.17.10 with a restrictive runtime permission override; see the evidence register. |
| cursor                 | `agents/cursor.sh`                 | `cursor-agent.cmd` | stable       | standard     | Qualified on Cursor Agent 2026.06.24 with headless workspace mode and runtime permission allowlists; see the evidence register. |
| kiro                   | `agents/kiro.sh`                   | `kiro-cli.exe` | stable       | standard     | Qualified on Kiro CLI 2.10.0 with non-interactive chat and restricted read/write trusted tools; see the evidence register. |
| qoder                  | `agents/qoder.sh`                  | `qodercli-1.0.30.exe` | stable       | standard     | Qualified on QoderCLI 1.0.30 with non-interactive mode and restricted read/write/edit/search tools; see the evidence register. |
| cline                  | Not registered                     | `cline`        | blocked      | experimental | Marker-file probe passed on Cline CLI 3.0.30, but runner probes failed and shell-command denial did not hold; no adapter is registered. |
| bad-commit-agent       | `agents/bad-commit-agent.sh`       | Git            | stable       | test-only    | Intentionally violates adapter contract by committing.                                                                        |
| bad-branch-agent       | `agents/bad-branch-agent.sh`       | Git            | stable       | test-only    | Intentionally violates adapter contract by switching branches.                                                                |
| bad-empty-agent        | `agents/bad-empty-agent.sh`        | Bash           | stable       | test-only    | Intentionally produces no patch.                                                                                              |
| bad-missing-cli-agent  | `agents/bad-missing-cli-agent.sh`  | Missing CLI    | stable       | test-only    | Intentionally fails closed when its required CLI cannot be resolved.                                                         |
| bad-outside-worktree-agent | `agents/bad-outside-worktree-agent.sh` | Bash        | stable       | test-only    | Intentionally writes an ignored file in the parent checkout to prove outside-worktree detection.                            |

## Adapter Acceptance Criteria

New adapters may become `standard` only after documented qualification:

* it is callable from Git Bash,
* three contiguous independent qualification cases pass through `qualify_adapter.sh`,
* each case satisfies the full runner safety contract and patch verification,
* each patch stays within its operator-controlled allowed-path list,
* each external acceptance test passes in a fresh verifier worktree, and
* the three results have the same complete pinned adapter configuration.

Promotion is separate from adapter qualification. Codex and Claude Code retain
their existing `standard` status under the grandfathered decision.

## Current Decision

`manual-simulated-agent`, `codex`, `claude-code`, `antigravity`, `copilot`,
`opencode`, `cursor`, `kiro`, and `qoder` are standard adapters. `cline` is
blocked and has no registered adapter script. Antigravity,
Copilot, OpenCode, Cursor, Kiro, and Qoder standard trust applies only to their recorded qualification
configurations;
adapter-script, CLI-version, model, or relevant configuration drift invalidates
that trust until requalification succeeds.

## Health-Proof CLI Preflight

`scripts/forge_check.sh` runs `scripts/check_adapters.sh` before its test
matrices. The `codex`, `claude`, `agy`, `copilot`, `opencode`,
`cursor-agent.cmd`, `kiro-cli.exe`, and `qodercli-1.0.30.exe` CLIs are required because they support
standard CLI adapters. CLI availability is an
environment precondition only; it does not change adapter trust or substitute
for captured run evidence.
