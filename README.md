Axiom Forge
Axiom Forge is a fail-closed verification and promotion gate for code produced by CLI coding agents.
It is not a general multi-agent orchestrator. It does not schedule autonomous work, manage agent conversations, merge to `main`, or run a dashboard.
The current v0.1 loop is:
```text
task file
  -> isolated agent worktree
  -> captured run directory
  -> patch verification
  -> explicit operator approval
  -> gate/<run-id> branch
  -> structured promotion record
````
Core Rule
Agents do not modify the main repository directly.
Agents may only modify disposable git worktrees. Axiom Forge captures their output as artifacts and promotes only through the gate.
What v0.1 Proves
Axiom Forge v0.1 proves that:
a task can be run through a provider adapter,
the adapter modifies only an isolated worktree,
the runner captures `patch.diff`,
the run is recorded in `record.json`,
the verifier recomputes pass or fail from a fresh worktree,
promotion requires exact operator approval,
promoted patches land on `gate/<run-id>`,
`main` remains unchanged,
failed runs remain inspectable but cannot promote.
Repository Shape
```text
agents/
  manual-simulated-agent.sh
  codex.sh
  claude-code.sh

scripts/
  run_agent_task.sh
  validate_run_dir.sh
  verify_patch.sh
  promote.sh
  forge_check.sh

tasks/
  *.task.md

tests/
  promote/run_all.sh
  runner/run_all.sh

runs/
  <run-id>/
    task.md
    record.json
    patch.diff
    stdout.log
    stderr.log
    promotion.json
```
`runs/` is ignored by git because run artifacts are local evidence, not source code.
Agent Adapter Contract
An adapter is an executable script:
```text
agents/<agent-name>.sh <task_file> <worktree>
```
The runner owns worktree creation, log capture, patch capture, and record writing.
The adapter may:
read the task file,
edit files inside the provided worktree,
run checks inside the provided worktree.
The adapter must not:
commit,
create or delete branches,
change `HEAD`,
modify files outside the provided worktree,
depend on access to the main repository.
If an adapter violates the contract, the runner records a failed run.
Run Directory Contract
A successful run directory contains:
```text
runs/<run-id>/
  task.md
  record.json
  patch.diff
  stdout.log
  stderr.log
```
A completed run has:
```json
{
  "run_status": "COMPLETED",
  "patch_file": "patch.diff"
}
```
A failed run has:
```json
{
  "run_status": "FAILED",
  "failure_reason": "<reason>"
}
```
Failed runs are evidence. They are not promotable inputs.
Promotion Contract
Promotion is performed with:
```bash
bash scripts/promote.sh "runs/<run-id>"
```
Promotion must:
validate the run directory,
reject stale base SHAs,
verify the patch from a disposable worktree,
require the operator to type the exact run id,
create `gate/<run-id>`,
apply and commit the patch there,
rerun verification,
write `promotion.json`.
Promotion must fail closed if any required condition is missing.
Health Check
Run the full local proof with:
```bash
bash scripts/forge_check.sh
```
Expected final line:
```text
AXIOM_FORGE_CHECK: PASS
```
This runs:
```bash
bash tests/promote/run_all.sh
bash tests/runner/run_all.sh
```
Example: Run a Task with Manual Adapter
```bash
bash scripts/run_agent_task.sh manual-simulated-agent tasks/change-answer.task.md
```
Then set the printed run id:
```bash
RUN_ID="<run-id>"
```
Verify:
```bash
bash scripts/validate_run_dir.sh "runs/$RUN_ID"
bash scripts/verify_patch.sh "runs/$RUN_ID"
```
Promote:
```bash
printf "%s\n" "$RUN_ID" | bash scripts/promote.sh "runs/$RUN_ID"
```
Example: Run a Task with Codex
```bash
bash scripts/run_agent_task.sh codex tasks/codex-change-answer.task.md
```
Then validate, verify, and promote the printed run id.
Example: Run a Task with Claude Code
```bash
bash scripts/run_agent_task.sh claude-code tasks/claude-change-answer.task.md
```
Then validate, verify, and promote the printed run id.
Current Non-Goals
Axiom Forge v0.1 does not implement:
generic multi-agent orchestration,
task decomposition,
autonomous scheduling,
dashboards or TUIs,
agent-to-agent messaging,
PR automation,
cloud routing,
local model runtime,
persistent autonomous agents,
cryptographic approvals,
container sandboxing.
Those features require evidence from actual run records or explicit operator decisions.
Baseline
The local v0.1 baseline is proven when:
```bash
bash scripts/forge_check.sh
```
returns:
```text
AXIOM_FORGE_CHECK: PASS
```
