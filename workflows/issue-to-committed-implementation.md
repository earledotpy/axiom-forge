# Issue to Committed Implementation Workflow

## Status

Ready for implementation.

## Purpose

Turn one bounded Axiom Forge GitHub issue or PRD slice into a validated local commit without expanding project scope or weakening gate behavior.

## Trigger

The workflow starts only when the user explicitly asks Codex to implement an issue with a command like:

```text
@implement Issue #N
```

Mentions of an issue during planning, review, status checks, or design discussion do not trigger implementation.

## Inputs

- The live GitHub issue or PRD slice that defines the requested change. Codex must fetch this before editing.
- The local `C:\axiom-forge` checkout.
- Repository instructions from `AGENTS.md`.

## Output

- A local git commit containing the bounded implementation.
- A concise report covering:
  - what changed
  - which files changed
  - which commands were run
  - whether validation passed or failed
  - whether `main` remained clean
  - remaining risks or follow-up work

## Guardrails

- Keep changes small and directly tied to the issue.
- Do not weaken validation, promotion, operator approval, clean-tree checks, stale-base checks, or gate-branch behavior.
- Do not edit run evidence files under `runs/<run-id>/`.
- Do not promote a run unless explicitly asked.
- Do not delete branches, remove worktrees, discard changes, or run destructive git commands without explicit approval.

## Initial Inspection

At the start of the workflow, Codex runs read-only inspection commands such as:

```bash
git status --short
git status -sb
git log --oneline -8
```

Codex uses this to record the starting branch and whether unrelated local changes already exist.

## Current Known Flow

1. Inspect repository state with read-only commands and record whether the worktree is already dirty.
2. Fetch and read the live GitHub issue or PRD slice; use pasted issue text only as context. If the live issue cannot be fetched, stop before editing.
3. Inspect relevant files and tests.
4. Make the smallest safe implementation change.
5. Select validation using the tiered validation policy.
6. Run the selected validation commands.
7. If validation passes and the diff is scoped to the issue, commit the scoped changes without an extra approval checkpoint.
8. Stop for a checkpoint instead of committing if the requirement is ambiguous, validation fails, unrelated dirty work blocks a clean commit, the fix would expand scope, or a needed command requires explicit approval.
9. Report the result in the repository-required format.

## Issue Fetch Policy

Codex must fetch the live GitHub issue or PRD slice before editing. Pasted or summarized issue text is context only.

If Codex cannot fetch the live issue, it must stop before editing. The checkpoint brief must say:

- which issue could not be fetched
- what fetch method failed
- what access or tooling is needed to proceed

## Validation Failure Policy

If validation fails after implementation, Codex may keep editing automatically only when the failure is clearly caused by Codex's own change and the fix remains within the issue scope.

Codex must stop for a checkpoint when the failure points to unrelated repo breakage, environment problems, missing external tools, ambiguous requirements, or a fix that would expand scope.

## Generated Evidence Policy

Codex must not stage generated evidence directories such as `runs/`.

Treat run artifacts as local evidence, not source code. Codex may reference paths to evidence in the final report, but it must not stage or hand-edit run artifacts unless the live issue explicitly asks to change tracked fixtures or documentation about evidence behavior.

## Scope Policy

Codex may fix nearby bugs or cleanup only when the change is necessary to satisfy the live issue and validation.

Otherwise, Codex leaves nearby findings alone and mentions them as follow-up risk or possible future work in the final report.

## Branch Policy

This workflow works on the current branch only.

It does not create branches, switch branches, create `gate/<run-id>` branches, or perform promotion behavior. If the issue requires any of those actions, Codex must stop for a checkpoint.

## Push Policy

This workflow does not push commits to GitHub automatically.

It stops at a local commit and final report. Publishing to a remote branch, opening a PR, or pushing `main` is handled by a separate explicit workflow.

## GitHub Issue Update Policy

This workflow does not comment on, label, or close GitHub issues automatically.

It produces a local commit and final report only. GitHub issue updates are handled by a separate explicit workflow because closing, labeling, or commenting changes project coordination state beyond implementation.

## Commit Message Policy

Automatic commits use a short imperative subject that names the issue when possible, for example:

```text
Implement issue #34 acceptance checks
```

Do not include a generated commit body unless the change needs important validation or scope notes. Keep detailed reporting in the final Codex response, not the commit body.

## Staging Policy

Codex may stage only files changed by this workflow run and directly required by the issue.

If a file had pre-existing user changes, Codex may stage only its own hunks when that can be done safely. If safe partial staging is not possible, Codex must stop for a checkpoint instead of creating a mixed commit.

## Dirty Worktree Policy

If the worktree is dirty at the start, Codex may continue only when the existing changes are clearly unrelated and can be left untouched.

Codex must:

- record the initial dirty state before editing
- avoid staging unrelated files
- stop for a checkpoint if dirty files overlap the issue
- stop for a checkpoint if dirty files block validation
- stop for a checkpoint if dirty files make a scoped commit unsafe

## Validation Policy

Codex chooses validation by change risk:

- Docs-only changes: run `git diff --check`; run no project scripts unless the issue asks for behavior validation.
- Focused code or test changes: run the narrow relevant test or script plus `git diff --check`.
- Shared gate, runner, verifier, promotion, or adapter-contract behavior: run the relevant focused test or script and `bash scripts/forge_check.sh` when the tree can be made clean enough for it.
- If `bash scripts/forge_check.sh` cannot run because unrelated dirty work exists, use a clean clone proof instead of mixing unrelated files into the commit.

The expected full proof final line is:

```text
AXIOM_FORGE_CHECK: PASS
```

## Checkpoint Policy

The workflow pushes the human checkpoint to the right: Codex should do the implementation work, run appropriate validation, and commit automatically when all of these are true:

- the trigger was `@implement Issue #N`
- the live issue requirements are clear
- validation passed
- the diff is scoped to the issue
- no unrelated dirty work prevents a clean scoped commit
- no destructive, promotion, branch deletion, reset, clean, or other approval-required command is needed

Codex must stop and ask for a checkpoint before committing when any of these are true:

- the issue requirements are ambiguous
- validation fails and cannot be fixed within the issue scope
- unrelated dirty work would be mixed into the commit
- the likely fix expands beyond the issue scope
- a required command needs explicit approval

## Checkpoint Brief

When Codex must stop for a human checkpoint, the brief contains only:

- the decision needed
- the blocking fact
- the proposed next action
- links or paths to relevant evidence

The brief does not dump raw diffs, logs, or drafts unless the user asks for them.