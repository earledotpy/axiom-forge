# Axiom Forge

Axiom Forge is a fail-closed verification and promotion gate for code produced by CLI coding agents.
It captures agent work as evidence, verifies patches from recorded bases, and promotes only after explicit operator approval.

Axiom Forge can operate in two explicit modes:

- Forge-local mode, where the Forge repository itself is the patch target.
- Target mode, where a configured external target repository is the patch target and Forge keeps the run, verification, and promotion evidence.

Axiom Forge is not a general multi-agent orchestrator. It does not schedule autonomous work, manage agent conversations, merge to `main`, or run a dashboard.

## The Loop

Forge-local mode:

```text
task file
  -> isolated agent worktree from the Forge repository
  -> captured run directory under runs/
  -> patch verification from the recorded Forge base
  -> explicit operator approval
  -> gate/<run-id> branch in the Forge repository
  -> structured promotion record
```

Target mode:

```text
task file in Forge
  -> configured external target repository preflight
  -> isolated agent worktree from the target repository
  -> captured run directory under Forge runs/
  -> target-owned patch verification from the recorded target base
  -> explicit operator approval
  -> gate/<run-id> branch in the target repository
  -> structured promotion record under Forge runs/
```

## Core Rules

Agents do not modify the main repository directly.
Agents may only modify disposable git worktrees created by the runner.
Axiom Forge captures their output as artifacts and promotes only through the gate.

In target mode, the external target repository receives only source changes from the promoted patch. Forge-owned task files, run records, logs, verification results, and promotion records remain in the Forge checkout under `runs/`.

Failed runs are evidence. They are not promotable inputs.

## Configured Target Repository

The primary external target repository is configured in `gate.toml`:

```toml
[target.primary]
name = "axiom"
repo_path = "C:/axiom"
expected_base_branch = "master"
expected_remote_url = "https://github.com/earledotpy/axiom.git"

[target.primary.verify]
command = ["python", "-m", "pytest"]
timeout_seconds = 300
```

The target preflight is local and fail-closed. It validates the configured path, Git root, `origin` URL, current branch, clean working tree, base SHA, and target verification command:

```bash
python scripts/target_preflight.py --config gate.toml --forge-root .
```

Expected success line:

```text
TARGET_PREFLIGHT: PASS
```

`target_preflight.py` is intentionally standalone. It is used by target-mode runs, but it is not part of `scripts/forge_check.sh`, so Forge's own health proof does not depend on the current state of the external target checkout.

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

An adapter earns `standard` trust by completing three consecutive, independent, in-scope qualification runs, one per case:

- `behavior-change`
- `new-behavior`
- `edge-case`

Each run must produce a verified patch and pass its task-specific acceptance test. A failed, unsafe, incomplete, task-incorrect, out-of-scope, or configuration-drifted run resets the series.

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

Interpret an adapter's committed qualification results as historical evidence under the compatibility/trust split, without requiring a `QUALIFIED` series and without touching `runs/`:

```bash
python scripts/qualification_report.py --adapter <adapter> --evidence-reuse
```

For each committed result, the report cites its source file under `qualification/results/<adapter>/` and states, independently, whether it proves candidate compatibility and whether it currently contributes to the adapter's standard trust series.

## Candidate Compatibility

A candidate adapter can be checked without running the full standard adapter qualification series:

```bash
bash scripts/check_candidate_adapter_compatibility.sh <adapter> <task-file>
```

The command runs the adapter through normal captured-run creation, run-directory validation, and patch verification. It writes `compatibility/results/<adapter>/<run-id>.json` with a `candidate_adapter_compatibility` result.

That result is compatibility evidence only. It is not `standard` trust, not adapter registration, and not promotion approval. Failed checks are still recorded as structured compatibility evidence with the stable failure reason from the failing stage.

Compatibility is intentionally weaker than qualification. Standard trust still requires the contiguous three-case qualification series, complete pinned adapter configuration evidence, task-specific acceptance, scope checks, and reset on failure, missing identity, task-incorrect behavior, out-of-scope changes, or configuration drift.

## Repository Shape

```text
agents/
  <adapter>.sh                      # operator-facing adapter scripts

compatibility/
  results/
    <adapter>/                      # local candidate compatibility results

docs/
  adapter-evidence.md               # committed qualification record and standard-adapter registry
  adr/                              # architecture decisions

qualification/
  adapters/
    <adapter>.json                  # adapter configuration declaration
  cases/
    behavior-change/                # task, allowed paths, acceptance test
    new-behavior/
    edge-case/
  results/
    <adapter>/                      # committed qualification results for that adapter

scripts/
  run_agent_task.sh                 # run one adapter against one task, optionally in target mode
  target_preflight.py               # validate the configured external target repository
  validate_run_dir.sh               # validate a captured run directory
  verify_patch.sh                   # verify a patch from a fresh worktree, optionally in target mode
  target_verify.py                  # target-mode context validation and target-owned verification
  promote.sh                        # gate and promote a verified run, optionally in target mode
  check_candidate_adapter_compatibility.sh
  qualify_adapter.sh
  forge_check.sh                    # full Forge-local health proof

  run_record.py
  write_run_record.py
  verifier_worktree.py
  compatibility_result.py
  write_compatibility_result.py
  qualification_case.py
  qualification_result.py
  write_qualification_result.py
  evaluate_qualification_series.py
  adapter_identity.py
  capture_cli_provenance.py
  qualification_report.py

tasks/
  *.task.md                         # operator-authored tasks for real agent runs

tests/
  gate_contract/run_all.sh          # static gate-contract matrix
  promote/run_all.sh                # Forge-local and target-mode promotion matrix
  runner/run_all.sh                 # Forge-local and target-mode runner matrix
  target_preflight/run_all.sh       # standalone target preflight matrix
  target_verify/run_all.sh          # target-mode verification matrix
  target_operator_loop/run_all.sh   # disposable end-to-end target operator loop
  compatibility/run_all.sh          # candidate compatibility matrix
  adapter_evaluation/run_all.sh     # compatibility/trust separation matrix
  qualification/run_all.sh          # qualification case matrix
  qualification_series/run_all.sh   # qualification series matrix
  test_*.py                         # Python unit tests

runs/
  <run-id>/
    task.md
    record.json
    patch.diff
    stdout.log
    stderr.log
    [target-preflight.json]         # present for successful target-mode runs
    [target-preflight.out]          # present for target-mode runs
    [verify.json]
    [post_verify.json]              # present after promotion reaches post-verify
    [qualification.json]            # present for qualification runs
    [promotion.json]                # present after promotion succeeds or fails closed
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

The runner snapshots Git status immediately before and after adapter execution. Any status change in the target checkout outside the runner's disposable worktree fails closed with `adapter_modified_outside_worktree`.

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

A completed run record contains:

```json
{
  "run_status": "COMPLETED",
  "patch_file": "patch.diff"
}
```

A failed run record contains:

```json
{
  "run_status": "FAILED",
  "failure_reason": "<reason>"
}
```

Target-mode completed records also include target identity fields:

```json
{
  "run_mode": "target",
  "target_name": "axiom",
  "target_repo": "C:/axiom",
  "target_base_branch": "master",
  "target_base_sha": "<sha>",
  "target_remote_url": "https://github.com/earledotpy/axiom.git",
  "base_sha": "<same target base sha>"
}
```

## Verification Contract

Forge-local verification:

```bash
bash scripts/verify_patch.sh "runs/<run-id>"
```

Target-mode verification requires the explicit target flag:

```bash
bash scripts/verify_patch.sh --target "runs/<run-id>"
```

Verification validates the run directory, creates a disposable verifier worktree from the recorded base, applies the patch with whitespace checks, runs the configured verification command, writes `verify.json`, and leaves no verifier worktree behind.

Target-mode verification additionally validates that the run record still matches the configured primary target repository before using the target repository as the verifier source.

## Promotion Contract

Forge-local promotion:

```bash
bash scripts/promote.sh "runs/<run-id>"
```

Target-mode promotion requires the explicit target flag:

```bash
bash scripts/promote.sh --target "runs/<run-id>"
```

Promotion validates the run directory, rejects stale base SHAs, verifies the patch before promotion, requires the operator to type the exact run ID, creates `gate/<run-id>`, applies and commits the patch there, reruns verification, and writes `promotion.json`.

In Forge-local mode, `gate/<run-id>` is created in the Forge repository. In target mode, `gate/<run-id>` is created in the configured external target repository while `promotion.json` remains under Forge's `runs/<run-id>/` evidence directory.

Promotion fails closed if any required condition is missing, including a dirty promotion repository, stale base SHA, existing gate branch, failed pre-promotion verification, failed operator approval, patch application failure, failed post-promotion verification, or target identity mismatch.

## Operator Workflow Examples

Forge-local run:

```bash
bash scripts/run_agent_task.sh claude-code tasks/change-answer.task.md
RUN_ID="<run-id>"
```

Forge-local validate, verify, and promote:

```bash
bash scripts/validate_run_dir.sh "runs/$RUN_ID"
bash scripts/verify_patch.sh "runs/$RUN_ID"
printf "%s\n" "$RUN_ID" | bash scripts/promote.sh "runs/$RUN_ID"
```

Target-mode run:

```bash
python scripts/target_preflight.py --config gate.toml --forge-root .
bash scripts/run_agent_task.sh --target claude-code tasks/change-answer.task.md
RUN_ID="<run-id>"
```

Target-mode validate, verify, and promote:

```bash
bash scripts/validate_run_dir.sh "runs/$RUN_ID"
bash scripts/verify_patch.sh --target "runs/$RUN_ID"
printf "%s\n" "$RUN_ID" | bash scripts/promote.sh --target "runs/$RUN_ID"
```

Before target promotion, review remains operator-driven: inspect `record.json`, `patch.diff`, `verify.json`, and the target diff. Formal review records are deferred for the first milestone.

## Health Check

```bash
bash scripts/forge_check.sh
```

Expected final line:

```text
AXIOM_FORGE_CHECK: PASS
```

The health proof requires a clean Forge working tree and the CLIs for all standard adapters to be present on the host.

`forge_check.sh` runs the adapter CLI preflight and nine test matrices that do not depend on the live external target checkout:

```bash
bash scripts/check_adapters.sh
bash tests/gate_contract/run_all.sh
bash tests/promote/run_all.sh
bash tests/runner/run_all.sh
bash tests/target_verify/run_all.sh
bash tests/target_operator_loop/run_all.sh
bash tests/compatibility/run_all.sh
bash tests/adapter_evaluation/run_all.sh
bash tests/qualification/run_all.sh
bash tests/qualification_series/run_all.sh
```

The standalone target preflight matrix is available separately:

```bash
bash tests/target_preflight/run_all.sh
```

## Non-Goals

Axiom Forge does not implement:

- generic multi-agent orchestration
- task decomposition or autonomous scheduling
- dashboards or TUIs
- agent-to-agent messaging or PR automation
- cloud routing or container sandboxing
- persistent autonomous agents
- cryptographic approvals
- arbitrary multi-target routing
- target-repository evidence storage

Any expansion beyond the current gate requires justification by a captured run, a recorded failure, or an explicit operator decision.
