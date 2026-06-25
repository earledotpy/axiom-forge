# Axiom Forge Codex Instructions

## Agent skills

### Issue tracker

Issues and PRDs live in GitHub Issues; external pull requests are not a triage surface. See `docs/agents/issue-tracker.md`.

### Triage labels

The canonical triage roles use the default GitHub label vocabulary. See `docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repository using the root `CONTEXT.md` and `docs/adr/`. See `docs/agents/domain.md`.

## Project purpose

Axiom Forge is a fail-closed verification and promotion gate for patches produced by CLI coding agents.

It is not a general multi-agent orchestrator, task scheduler, dashboard, cloud router, local model runtime, or persistent autonomous agent system.

The current project goal is to preserve a narrow v0.1 loop:

```text
task file
  -> isolated agent worktree
  -> captured run directory
  -> patch verification
  -> explicit operator approval
  -> gate/<run-id> branch
  -> structured promotion record
```

## Core invariants

* Agents must not modify the main repository directly.
* Agents may only modify disposable git worktrees created by the runner.
* Captured run artifacts are evidence.
* Failed runs are evidence, not promotable inputs.
* Promotion must fail closed if required conditions are missing.
* `main` must remain unchanged by agent work.
* Promoted patches must land on `gate/<run-id>` branches.
* Do not weaken the gate to make an adapter, run, test, or promotion pass.
* Do not expand scope beyond the patch gate without explicit operator direction.

## Repository shape

Important paths:

```text
agents/   adapter scripts
scripts/  runner, verification, promotion, and health-check scripts
tasks/    task files
tests/    proof and regression test scripts
docs/     operator documentation
runs/     local captured run artifacts; ignored by git
```

Treat `runs/` as local evidence, not source code.

Do not hand-edit these run evidence files:

```text
runs/<run-id>/patch.diff
runs/<run-id>/record.json
runs/<run-id>/promotion.json
```

## Development rules

* Keep changes small and directly tied to the requested task.
* Prefer preserving the existing Bash-based design unless the task explicitly requires a different implementation.
* Do not introduce orchestration, dashboards, autonomous scheduling, cloud routing, persistent agents, or container sandboxing unless explicitly requested.
* Do not rename core scripts or change their command-line contracts without explicit approval.
* Do not bypass validation, operator approval, stale-base checks, clean-tree checks, or gate-branch creation.
* Do not convert fail-closed behavior into best-effort behavior.
* When changing adapter behavior, preserve the rule that adapters must not commit, create or delete branches, change `HEAD`, modify files outside the provided worktree, or depend on access to the main repository.
* When changing promotion behavior, preserve exact operator approval and promotion to `gate/<run-id>`.

## Command safety

Before running commands that mutate repository state, explain what they do.

Be especially careful with:

```bash
git switch
git branch
git worktree
git reset
git clean
bash scripts/promote.sh
```

Do not delete branches, remove worktrees, discard changes, or promote a run unless explicitly asked.

## Standard inspection commands

At the start of work, prefer read-only inspection:

```bash
git status --short
git status -sb
git log --oneline -8
git tag --list "v0.1*"
```

## Validation

The full local proof is:

```bash
bash scripts/forge_check.sh
```

Expected final line:

```text
AXIOM_FORGE_CHECK: PASS
```

This check requires a clean working tree.

When diagnosing adapter CLI availability, use:

```bash
bash scripts/check_adapters.sh
```

When validating a captured run, use:

```bash
bash scripts/validate_run_dir.sh "runs/<run-id>"
```

When verifying a patch, use:

```bash
bash scripts/verify_patch.sh "runs/<run-id>"
```

Do not promote unless validation and verification pass.

## Promotion rules

Promotion is performed with:

```bash
bash scripts/promote.sh "runs/<run-id>"
```

Promotion must:

* validate the run directory
* reject stale base SHAs
* verify the patch from a disposable worktree
* require exact operator approval
* create `gate/<run-id>`
* apply and commit the patch there
* rerun verification
* write `promotion.json`

Do not promote if:

* `validate_run_dir.sh` fails
* `verify_patch.sh` fails
* `record.json` is missing or malformed
* `run_status` is `FAILED`
* `failure_reason` is non-null
* `patch.diff` is missing or empty
* `base_sha` is stale
* the patch has whitespace errors
* operator approval does not match the exact run id
* `gate/<run-id>` already exists
* the diff touches files outside the task scope

## Reporting format

After making changes, report:

1. What changed
2. Which files changed
3. Which commands were run
4. Whether validation passed or failed
5. Whether `main` remained clean
6. Any remaining risks or follow-up work

If validation was not run, explain why.

