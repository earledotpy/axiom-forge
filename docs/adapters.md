# Adapter Registry

This file records the known Axiom Forge agent adapters.

The adapter contract is:

```text
agents/<agent-name>.sh <task_file> <worktree>
````

The runner creates the worktree, calls the adapter, captures logs, captures the patch, and writes `record.json`.

Adapters are not trusted to promote code. Promotion is always handled by `scripts/promote.sh`.

## Status Levels

```text
stable        Passes the runner contract and has produced a promoted gate branch.
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
| antigravity            | `agents/antigravity.sh`            | `agy`          | experimental | experimental | Callable through Git Bash as `agy` 1.0.8. Produced a promoted gate branch, but first run exposed whitespace hygiene warnings. |
| bad-commit-agent       | `agents/bad-commit-agent.sh`       | Git            | stable       | test-only    | Intentionally violates adapter contract by committing.                                                                        |
| bad-branch-agent       | `agents/bad-branch-agent.sh`       | Git            | stable       | test-only    | Intentionally violates adapter contract by switching branches.                                                                |
| bad-empty-agent        | `agents/bad-empty-agent.sh`        | Bash           | stable       | test-only    | Intentionally produces no patch.                                                                                              |

## Adapter Acceptance Criteria

An adapter may become `standard` only if:

* it is callable from Git Bash,
* it can run from `run_agent_task.sh`,
* it edits only the provided worktree,
* it does not commit,
* it does not create or delete branches,
* it does not change `HEAD`,
* it leaves a non-empty patch,
* the patch passes `verify_patch.sh`,
* the patch promotes through `promote.sh`,
* `forge_check.sh` passes after the adapter is added.

## Current Decision

`manual-simulated-agent`, `codex`, and `claude-code` are standard adapters.

`antigravity` remains experimental until it can repeatedly produce whitespace-clean patches under the hardened gate.
