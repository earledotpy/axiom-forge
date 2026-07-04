# Integrate Axiom Forge with a configured external target repository

Axiom Forge will target the Axiom system as a configured external target repository rather than being embedded in the target worktree or accepting arbitrary target paths on each command. The first integration milestone extends Forge-owned configuration in `gate.toml` for one primary target, keeps captured run and promotion evidence under Axiom Forge's `runs/`, promotes verified patches onto `gate/<run-id>` branches in the external target repository, and runs target-owned verification checks in disposable target verifier worktrees. Target runs must fail closed unless the configured target exists, is a Git repository, is on the expected base branch, and has a clean working tree before the run starts, because otherwise Forge cannot prove which changes came from the agent-produced patch.

Target-repo support should generalize the existing runner, verifier, and promotion scripts carefully rather than creating a parallel target-only command set. The existing scripts already encode Axiom Forge's fail-closed safety rules, so the implementation should preserve the operator-facing loop while moving repository/worktree ownership behind shared internals that can operate on the Forge repository or the configured external target repository.

Target-repo operation should require an explicit target mode flag at first. Adding [target] configuration must not silently change existing Forge-repo command behavior; the operator must opt into the configured primary target repository for run, verify, and promote commands during the first integration milestone.

Target-mode run records should preserve the existing record schema for Forge-local runs and add target identity fields only when explicit target mode is used. Target validation should require those target fields for target-mode runs, while existing Forge-local run evidence remains valid without migration.

Target-mode task files should remain Forge-owned at first, using the existing `tasks/` directory as operator intent and run input evidence. The external target repository should receive only agent-produced source changes through disposable worktrees and target promotion, not Forge task files or run evidence.

Formal review records are deferred from the first target-repo milestone. Review remains operator-driven inspection of the Forge-owned captured patch and run evidence before explicit target promotion, so the first milestone can prove target run, target verification, and target promotion before adding another evidence type.

Target promotion keeps the existing `gate/<run-id>` branch naming convention in the external target repository. The repository location and promotion evidence distinguish target promotion from Forge-local promotion, while the branch name stays tied directly to the captured run ID.

The first implementation slice should be a read-only target repository preflight before any target-mode run support is added. The preflight should read `gate.toml` and fail closed unless the configured target exists, is outside the Forge checkout, is a Git repository, is on the expected base branch, has a clean working tree, can resolve its base SHA, and has target-owned verification configured.

The target repository preflight should be standalone first and should not be added to `forge_check.sh` immediately. Target-mode commands should reuse the preflight internally later, but Forge's own health proof should remain independent of the external target repository until target integration is stable.

Target repository preflight should validate both the configured filesystem path and the expected Git remote URL. A clean Git repository at the configured path is not enough by itself; the preflight should fail closed if the target repository's `origin` does not match the configured expected remote for the Axiom system repository.

The first target repository preflight should inspect local repository state only and should not contact the remote. Remote freshness checks can be added later, but the initial preflight should avoid network and authentication failure modes by validating the local path, Git root, `origin` URL, branch, clean state, base SHA, and configured target verification command.

Target-owned verification should be configured as a single command array with a timeout for the first milestone, rather than a named matrix of checks. A single command is enough to prove target patch verification in a disposable target verifier worktree; named lint/test/typecheck matrices can be introduced later if the Axiom system workflow needs separate reporting.