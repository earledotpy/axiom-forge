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

Known standard adapters are listed in `docs/adapters.md`. Before using a
standard CLI adapter, confirm the local CLI preflight passes:

```bash
bash scripts/check_adapters.sh
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

## Run A Target-Mode Task

Use target mode when the patch target is the configured external target repository instead of the Forge checkout. In the first milestone there is one primary target repository configured in `gate.toml`; arbitrary multi-target routing is intentionally out of scope.

Run the standalone target preflight first:

```bash
python scripts/target_preflight.py --config gate.toml --forge-root .
```

Required success:

```text
TARGET_PREFLIGHT: PASS
```

The target preflight validates the configured path, Git root, `origin` URL, current base branch, clean working tree, base SHA, and target-owned verification command. It is separate from `scripts/forge_check.sh` at first so Forge's full health proof does not depend on the current state of the real external target repository.

Run the adapter with the explicit target flag:

```bash
bash scripts/run_agent_task.sh --target <agent-name> <task-file>
RUN_ID="<run-id>"
```

In target mode, task files and captured run evidence remain Forge-owned under `runs/<run-id>/`. The external target repository is used to create the disposable agent worktree and later receives the promoted `gate/<run-id>` branch during target promotion.

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

For a target-mode run, also check:

```text
run_mode is target
target_name is the configured primary target repository
target_repo points to the external target repository
target_base_branch is the expected target base branch
target_base_sha matches the recorded base_sha
target_remote_url is the expected origin URL
target-preflight.json exists under runs/<run-id>/
```

Review remains operator-driven for the first milestone. There is no formal review-record artifact yet; inspect `record.json`, `patch.diff`, `verify.json`, and the relevant target repository diff before promotion.

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

Target-mode verification requires the explicit target flag:

```bash
bash scripts/verify_patch.sh --target "runs/$RUN_ID"
```

This performs target-owned verification from the external target repository's recorded base and writes `runs/<run-id>/verify.json` in Forge-owned evidence.

Common verification failures:

```text
patch_check_failed       patch does not apply cleanly or has whitespace errors
VERIFY_TARGET failure    patch applies but target verification fails
stale base SHA           run was produced against a base that is no longer current
```

## Check A Candidate Adapter

Use candidate compatibility when the question is whether a future AI CLI can
operate through Axiom Forge's normal captured-run and verified-patch path. This
is the lightweight intake path for a new CLI before deciding whether to spend
time on standard qualification:

```bash
bash scripts/check_candidate_adapter_compatibility.sh <adapter> <task-file>
```

The check creates a normal captured run, validates the run directory, verifies
the patch, and writes a local compatibility result under:

```text
compatibility/results/<adapter>/<run-id>.json
```

Interpretation:

```text
PASS means the candidate configuration completed the captured-run and verified-patch path once.
FAIL means the result is still evidence, with a stable failure reason from the failed stage.
```

A candidate compatibility result is not adapter registration, not `standard`
trust, not qualification evidence, and not promotion approval. Do not update
`docs/adapters.md` to `standard` from a compatibility result alone.

## Qualify A Standard Adapter

Use standard qualification when the decision is whether a registered adapter
configuration should receive or retain `standard` trust. Qualification is still
required after adapter-script, CLI-version, selected-model, or relevant
configuration drift.

Run one case:

```bash
bash scripts/qualify_adapter.sh <adapter> <case>
```

Run all three independent cases for a complete standard-trust series:

```text
behavior-change
new-behavior
edge-case
```

Evaluate the committed result series:

```bash
python scripts/evaluate_qualification_series.py --adapter <adapter>
```

Generate the review snippet for the evidence register:

```bash
python scripts/qualification_report.py --adapter <adapter>
```

Standard qualification is stronger than candidate compatibility because it
requires three contiguous successful cases, complete pinned configuration
identity, task-specific acceptance, allowed-path scope checks, and reset on
failure or configuration drift.

Qualification decides adapter trust only. It does not promote any captured run;
promotion still requires `verify_patch.sh` and `promote.sh` with exact operator
approval.

Policy reference: `docs/adr/0001-contiguous-adapter-qualification.md` keeps
compatibility as a weaker pre-registration decision and preserves contiguous
qualification as the rule for `standard` trust.

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

For target promotion, use the explicit target flag:

```bash
printf "%s\n" "$RUN_ID" | bash scripts/promote.sh --target "runs/$RUN_ID"
```

Target promotion creates `gate/<run-id>` in the external target repository, not in the Forge repository. `promotion.json` remains Forge-owned under `runs/<run-id>/`.

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

For target promotion, inspect the branch in the external target repository:

```bash
git -C <target-repo> diff <target-base-branch>.."gate/$RUN_ID"
cat "runs/$RUN_ID/promotion.json"
git -C <target-repo> branch --show-current
git -C <target-repo> status --short
```

Check:

```text
gate/<run-id> exists in the external target repository
the target base branch remains unchanged
promotion.json records target_name, target_repo, target_base_branch, and promotion_commit
Forge remains on main unless you intentionally switched it
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

Standard adapter CLI dependencies are listed in `docs/adapters.md`; missing dependencies fail both this preflight and `forge_check.sh`.

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
adapter name
CLI command, resolved path, and version
run ID and base SHA
whether the evidence is a compatibility result, qualification result, or promotion result
verification result
promotion result and gate branch, if promotion was explicitly performed
failure reason, if the run failed closed
short decision summary
```

Keep the evidence categories separate:

```text
candidate compatibility: local evidence that one candidate can complete the captured-run and verified-patch path
standard qualification: committed evidence for a pinned adapter configuration's standard trust
promotion: operator-approved movement of one verified patch onto gate/<run-id>
```
