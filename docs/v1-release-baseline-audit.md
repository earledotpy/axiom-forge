# Axiom Forge v1 release-baseline audit

**Retrieved:** 2026-07-14T01:50:10-06:00  
**Scope:** Read-only evidence for [Audit the authoritative Axiom Forge v1 release baseline](https://github.com/earledotpy/axiom-forge/issues/57). This is a baseline audit, not a release declaration.

## Findings

1. The current checkout is not a releasable health-proof surface. It is on
   `issue-54-operator-directed-retry` at `7bf420c`, with pre-existing changes
   in `app/workbench.py` and `tests/test_workbench.py` (220 insertions and two
   deletions). `git diff --check` reported no whitespace errors; its only
   output was CRLF conversion warnings. Those changes must be preserved and
   must not be attributed to this audit.

2. The remote default branch is current, but the local tracking ref is stale.
   Authenticated GitHub API evidence reports remote `main` at
   `355b87493dc045aa59a4d6b7560fbd5da91310c9`, identical to local `main`.
   The local `origin/main` ref is `0d01ae8905cba736e3776b132faac86ed26c5894`,
   so the local `main...origin/main` count of `10 0` is not unpublished-work
   evidence. The repository API also reports `main` as the default branch and
   a latest push at `2026-07-13T05:25:46Z`.

3. There is no v1 release tag. `git tag --list "v1*"` returned no local tags,
   and the authenticated GitHub tags API returned no remote tags. The two
   local-only historical tags are `v0.1` (annotated; resolves to `3dbef2f`,
   2026-06-17) and `v0.1-local` (`3629760`, 2026-06-16). The operator runbook
   explicitly says not to move `v0.1-local` and to use a new tag for a later
   release point.[^runbook]

4. The focused workbench suite currently passes: `python -B -m unittest
   tests.test_workbench` completed **35 tests in 18.085 seconds** with `OK`.
   This is narrow evidence only; it does not replace the full health proof.

5. A current full-health pass cannot be claimed. `scripts/forge_check.sh`
   first checks for a clean working tree and exits before running any matrix
   when the tree is dirty.[^forge-check] Therefore neither full-health stage
   timings nor `AXIOM_FORGE_CHECK: PASS` are available from this checkout.
   A clean, immutable validation surface is required before that proof can be
   collected.

6. GitHub API authentication works (`gh auth status` identified the active
   `earledotpy` account with `repo` and `workflow` scopes), but native Git
   HTTPS access failed during `git ls-remote` with
   `schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS`.
   Release operations relying on native Git network transport need a separate
   credential repair or validation, even though the GitHub API was usable for
   this audit.

## Release-baseline blockers to resolve

- Preserve or isolate the existing worktree changes, then obtain one full
  clean-tree health proof with per-stage timing.
- Decide and create the first v1 release tag only after the health proof and
  release criteria are settled; do not retag either local v0.1 marker.
- Repair or otherwise validate native Git HTTPS authentication before an
  operation that must fetch, push, or publish a tag.
- Refresh the local `origin/main` tracking ref only as part of an explicitly
  authorized repository-recovery action; it is not evidence that remote
  `main` is behind.

## Evidence and methods

All commands below were read-only except the focused unittest's normal
temporary test activity; no repository source, test, run-evidence, Git,
worktree, branch, tag, or promotion state was changed.

| Question | Evidence command or source | Result |
| --- | --- | --- |
| Checkout and uncommitted changes | `git status -sb`; `git diff --stat`; `git diff --check` | `issue-54-operator-directed-retry`; two modified files; clean diff check apart from CRLF warnings. |
| Current commits and cached divergence | `git rev-parse main origin/main HEAD`; `git rev-list --left-right --count main...origin/main` | `main=355b874`, `origin/main=0d01ae8`, `HEAD=7bf420c`; cached divergence `10 0`. |
| Authoritative remote main and tags | `gh api repos/earledotpy/axiom-forge/git/ref/heads/main`; `gh api repos/earledotpy/axiom-forge/tags --paginate`; `gh api repos/earledotpy/axiom-forge` | remote `main=355b874`; no remote tags; default branch and latest-push facts above. |
| Authentication | `gh auth status`; `git ls-remote --heads origin` | GitHub API authenticated; native Git HTTPS credential failure. |
| Focused regression | `python -B -m unittest tests.test_workbench` | 35 tests, 18.085 seconds, `OK`. |
| Full-health contract | [`scripts/forge_check.sh`](../scripts/forge_check.sh) | Clean-tree guard precedes every validation stage. |

[^runbook]: [`docs/operator-runbook.md`](operator-runbook.md), "Operating Rules" and "Start Of Session" (read 2026-07-14): requires `main` and a clean tree for health checks, and says not to move `v0.1-local`.
[^forge-check]: [`scripts/forge_check.sh`](../scripts/forge_check.sh) (read 2026-07-14): the `git status --porcelain` guard precedes adapter preflight, matrices, and the final pass sentinel.
