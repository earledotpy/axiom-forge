# Axiom Forge Operator Runbook

Purpose: operate the Axiom Forge v0.1 patch gateway from Git Bash without relying on chat history.

Axiom Forge does not trust agent claims. It trusts captured artifacts, recomputed verification, explicit operator approval, and promotion records.

## Operating Rules

- Work from `main`.
- Keep the working tree clean before running health checks or promotion.
- Agents may edit only disposable worktrees created by the runner.
- A run that changes the target checkout outside its worktree fails with `adapter_modified_outside_worktree`; this detects checkout changes, not arbitrary host-path writes.
- Do not edit `runs/<run-id>/patch.diff`, `record.json`, or `promotion.json` by hand.
- Do not promote a run unless `verify_patch.sh` passes.
- Do not weaken the gate to make an adapter pass.
- Clean target, current base, exact operator approval, and no existing gate branch are fixed fail-closed invariants, not configurable switches.
- Do not move `v0.1-local`; use new release tags for later release points.

## Start Of Session

```bash
cd /c/axiom-forge

git status --short
git status -sb
git log --oneline -8
git tag --list "v0.1*"
git remote -v
```

Expected:

```text
working tree clean
branch main
origin points to https://github.com/earledotpy/axiom-forge.git
```

Run the health proof:

```bash
bash scripts/forge_check.sh
```

Expected final line:

```text
AXIOM_FORGE_CHECK: PASS
```

The health proof includes an adapter CLI preflight. Run it directly when
diagnosing the local environment:

```bash
bash scripts/check_adapters.sh
```

Expected final line:

```text
ADAPTER_SMOKE_CHECK: PASS
```

## Run An Adapter Task

Use this form:

```bash
bash scripts/run_agent_task.sh <agent-name> <task-file>
```

Known adapters:

```text
manual-simulated-agent
codex
claude-code
antigravity
```

Examples:

```bash
bash scripts/run_agent_task.sh codex tasks/codex-change-answer.task.md
bash scripts/run_agent_task.sh claude-code tasks/claude-change-answer.task.md
bash scripts/run_agent_task.sh antigravity tasks/antigravity-change-answer.task.md
```

The runner prints:

```text
RUN_CAPTURED: <run-id>
RUN_DIR: runs/<run-id>
```

Set the run id:

```bash
RUN_ID="<run-id>"
```

If you missed it:

```bash
RUN_ID="$(basename "$(ls -td runs/* | head -1)")"
echo "$RUN_ID"
```

## Inspect A Captured Run

```bash
bash scripts/validate_run_dir.sh "runs/$RUN_ID"
cat "runs/$RUN_ID/record.json"
```

Check:

```text
run_id exactly matches the directory name (enforced by validate_run_dir.sh)
agent is the adapter you intended to run
base_sha is the expected base commit
run_status is COMPLETED before promotion is considered
patch_file is patch.diff
patch_sha256 is present
cli_command identifies the invoked CLI for a real adapter
cli_path is the resolved executable that produced the patch
cli_version is the best-effort version observation (or null if unavailable)
failure_reason is null
```

Important: `run_status: COMPLETED` means the adapter produced a captured run. It does not mean the patch is safe to promote.

## Verify A Patch

```bash
bash scripts/verify_patch.sh "runs/$RUN_ID"
```

Required success:

```text
VERIFY_TARGET: PASS
VERIFY_PATCH: PASS <run-id>
```

If this fails, do not promote. Treat the run as evidence.

Common verification failures:

```text
patch_check_failed       patch does not apply cleanly or has whitespace errors
VERIFY_TARGET failure    patch applies but target verification fails
stale base SHA           run was produced against a base that is no longer current
```

## Promote A Verified Run

Only promote after validation and verification pass:

```bash
printf "%s\n" "$RUN_ID" | bash scripts/promote.sh "runs/$RUN_ID"
```

Promotion requires exact operator approval:

```text
Type the exact run id to continue:
```

Expected success:

```text
OPERATOR_APPROVAL: PASS <run-id>
PROMOTED: <run-id> -> gate/<run-id>
COMMIT: <promotion-commit>
```

Promotion must create a gate branch, not modify `main`.

## Inspect A Promotion

```bash
git diff main.."gate/$RUN_ID"
cat "runs/$RUN_ID/promotion.json"
git branch --show-current
git status --short
```

Check:

```text
branch is gate/<run-id>
status is PROMOTED
promotion_commit is present
main remains clean
diff scope matches the task
```

If Git switches you away from `main`, return:

```bash
git switch main
```

## Do Not Promote These Runs

Do not promote if any of these are true:

```text
validate_run_dir.sh fails
verify_patch.sh fails
record.json is missing or malformed
run_status is FAILED
failure_reason is non-null
patch.diff is missing or empty
base_sha is stale
patch has whitespace errors
operator approval does not match the exact run id
gate/<run-id> already exists
the diff touches files outside the task scope
```

## Recovery Guide

Dirty working tree:

```bash
git status --short
```

If the dirty files are expected source changes, commit or discard them intentionally before running health checks. Do not promote from a dirty source tree.

Adapter missing:

```bash
bash scripts/check_adapters.sh
```

`codex`, `claude`, and `agy` are required because they back the standard CLI
adapters; their absence fails both this preflight and `forge_check.sh`.

Patch whitespace failure:

```text
ERROR: patch_check_failed
```

Decision: do not promote. Record the adapter result and rerun a new task if needed. Do not edit `patch.diff` by hand.

Existing gate branch:

```bash
git branch --list "gate/$RUN_ID"
```

Decision: do not reuse the run id. Use a new run.

Failed run record:

```bash
cat "runs/$RUN_ID/record.json"
```

Decision: treat it as evidence. Do not promote.

## Evidence To Record

For real adapter milestones, record:

```text
