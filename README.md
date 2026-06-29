# Axiom Forge

Axiom Forge is a fail-closed verification and promotion gate for code produced by CLI coding agents.
It is not a general multi-agent orchestrator. It does not schedule autonomous work, manage agent conversations, merge to `main`, or run a dashboard.

## The Loop

```text
task file
  -> isolated agent worktree
  -> captured run directory
  -> patch verification
  -> explicit operator approval
  -> gate/<run-id> branch
  -> structured promotion record
```

## Core Rule

Agents do not modify the main repository directly.
Agents may only modify disposable git worktrees. Axiom Forge captures their output as artifacts and promotes only through the gate.

## Standard Adapters

Nine adapters hold `standard` trust after completing the three-case qualification series:

| Adapter | CLI |
| --- | --- |
| `antigravity` | `agy` |
| `codex` | `codex` |
| `claude-code` | `claude` |
| `copilot` | `copilot` |
| `opencode` | `opencode` |
| `cursor` | `cursor-agent.cmd` |
| `kiro` | `kiro-cli.exe` |
| `qoder` | `qodercli-1.0.30.exe` |
| `kilo` | `kilo` |

Standard trust is configuration-pinned. Any change to an adapter's script revision, CLI version, selected model, or relevant configuration invalidates standard status until a new qualification series succeeds.

Qualification evidence and pinned configurations are recorded in `docs/adapter-evidence.md`.

## Adapter Qualification

An adapter earns `standard` trust by completing three consecutive, independent, in-scope qualification runs — one per case (`behavior-change`, `new-behavior`, `edge-case`) — each producing a verified patch and passing its task-specific acceptance test. A failed, unsafe, or incomplete run resets the series.

Run a single qualification case:

```bash
bash scripts/qualify_adapter.sh <adapter> <case>
```

Evaluate a completed result series:

```bash
python scripts/evaluate_qualification_series.py --adapter <adapter>
```

Generate a reviewable Markdown snippet for `docs/adapter-evidence.md`:

```bash
python scripts/qualification_report.py --adapter <adapter>
```

The snippet is printed to stdout for operator review before any doc is updated.

## Repository Shape

```text
agents/
  <adapter>.sh                   # operator-facing adapter scripts

docs/
  adapter-evidence.md            # committed qualification record and standard-adapter registry

qualification/
  adapters/
    <adapter>.json               # adapter configuration declaration (model, relevant config)
  cases/
    behavior-change/             # task, allowed-paths, acceptance test
    new-behavior/
    edge-case/
  results/
    <adapter>/                   # committed qualification results for that adapter

scripts/
  run_agent_task.sh              # run one adapter against one task
  validate_run_dir.sh            # validate a captured run directory
  verify_patch.sh                # verify a patch from a fresh worktree
  promote.sh                     # gate and promote a verified run
  qualify_adapter.sh             # run one qualification case end-to-end
  forge_check.sh                 # full local health proof

  run_record.py                  # run record schema and validation library
  write_run_record.py            # CLI: write a run record
  verifier_worktree.py           # patch apply and target verification library
  qualification_case.py          # qualification case loading library
  qualification_result.py        # qualification result building and series evaluation
  write_qualification_result.py  # CLI: write a qualification result
  evaluate_qualification_series.py  # CLI: evaluate a result series
  adapter_identity.py            # adapter identity validation and CLI provenance capture
  capture_cli_provenance.py      # CLI: capture CLI provenance (delegates to adapter_identity)
  qualification_report.py        # library + CLI: render Markdown qualification snippets

tasks/
  *.task.md                      # operator-authored tasks for real agent runs

tests/
  gate_contract/run_all.sh       # gate failure and success contract matrix
  promote/run_all.sh             # promotion matrix
  runner/run_all.sh              # runner matrix
  qualification/run_all.sh       # qualification case matrix
  qualification_series/run_all.sh # qualification series matrix
  test_run_record.py             # run record unit tests
  test_verifier_worktree.py      # verifier worktree unit tests
  test_qualification_modules.py  # qualification case/result unit tests
  test_adapter_identity.py       # adapter identity unit tests
  test_qualification_report.py   # qualification report unit tests

runs/
  <run-id>/
    task.md
    record.json
    patch.diff
    stdout.log
    stderr.log
    [qualification.json]         # present for qualification runs
    [promotion.json]             # present after promotion
```

`runs/` is gitignored. Run artifacts are local evidence, not source code.

## Agent Adapter Contract

An adapter is an executable script:

```text
agents/<adapter>.sh <task_file> <worktree>
```

The runner owns worktree creation, log capture, patch capture, and record writing. The adapter may read the task file and edit files inside the provided worktree.

The adapter must not commit, create or delete branches, change `HEAD`, modify files outside the provided worktree, or depend on access to the main repository.

If an adapter violates the contract, the runner records a failed run.

The runner snapshots git status immediately before and after adapter execution. Any status change in the target checkout outside the runner's disposable worktree fails closed with `adapter_modified_outside_worktree`.

## Run Directory Contract

A completed run directory contains:

```text
runs/<run-id>/
  task.md
  record.json
  patch.diff
  stdout.log
  stderr.log
```

A completed run record:

```json
{
  "run_status": "COMPLETED",
  "patch_file": "patch.diff"
}
```

A failed run record:

```json
{
  "run_status": "FAILED",
  "failure_reason": "<reason>"
}
```

Failed runs are evidence. They are not promotable inputs.

## Promotion Contract

```bash
bash scripts/promote.sh "runs/<run-id>"
```

Promotion validates the run directory, rejects stale base SHAs, verifies the patch from a disposable worktree, requires the operator to type the exact run ID, creates `gate/<run-id>`, applies and commits the patch there, reruns verification, and writes `promotion.json`. It fails closed if any required condition is missing.

## Operator Workflow Example

Run a task:

```bash
bash scripts/run_agent_task.sh claude-code tasks/change-answer.task.md
RUN_ID="<run-id>"
```

Validate and verify:

```bash
bash scripts/validate_run_dir.sh "runs/$RUN_ID"
bash scripts/verify_patch.sh "runs/$RUN_ID"
```

Promote:

```bash
printf "%s\n" "$RUN_ID" | bash scripts/promote.sh "runs/$RUN_ID"
```

## Health Check

```bash
bash scripts/forge_check.sh
```

Expected final line:

```text
AXIOM_FORGE_CHECK: PASS
```

This runs the adapter CLI preflight and all five test matrices:

```bash
bash scripts/check_adapters.sh
bash tests/gate_contract/run_all.sh
bash tests/promote/run_all.sh
bash tests/runner/run_all.sh
bash tests/qualification/run_all.sh
bash tests/qualification_series/run_all.sh
```

The health proof requires the CLIs for all standard adapters to be present on the host.

## Non-Goals

Axiom Forge does not implement:

- generic multi-agent orchestration
- task decomposition or autonomous scheduling
- dashboards or TUIs
- agent-to-agent messaging or PR automation
- cloud routing or container sandboxing
- persistent autonomous agents
- cryptographic approvals

Any expansion beyond the current gate requires justification by a captured run, a recorded failure, or an explicit operator decision.
