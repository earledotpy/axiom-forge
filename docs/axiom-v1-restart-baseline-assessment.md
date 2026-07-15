# Axiom v1 restart baseline and acceptance-task assessment

Date: 2026-07-14

## Scope and evidence

This is a read-only assessment of `C:\axiom` at local `master` commit
`78a9679` (one commit ahead of `origin/master`). `git status -sb` reported no
working-tree changes. The remote repository has no open GitHub issues.

The target is explicitly a legacy reference, suspended on 2026-06-10. Its
documented operational state is `fail_closed_non_autonomous`; the README and
governance doctrine prohibit implicit runtime, IPC, network, sandbox, or
autonomy activation.

Useful foundations already present:

- The numbered governance scaffold and JSON record schemas, checked by
  `tools/validate_governance.py` and `tests/test_validate_governance.py`.
- Bootstrap and foundation verification commands with deterministic CLI tests,
  including `tools/bootstrap_check.py` and `tests/test_bootstrap_check_cli.py`.
- A large existing pytest suite covering state, policy, governance, scheduler,
  and Level 2A boundaries.

## Boundary and drift findings

- The repository has substantial legacy/runtime scaffolding; gateway and agent
  activation, IPC reactivation, autonomy, and broad redesign are unsuitable
  first acceptance changes.
- Several scripts and tests retain the historical `C:\axiom` location. In
  particular, `tests/test_bootstrap_check_cli.py` executes
  `C:\axiom\tools\bootstrap_check.py`, rather than the checkout containing
  the test. In a Forge disposable worktree, that can validate the primary
  checkout instead of the candidate patch.
- The bootstrap CLI itself resolves its repository root from its own file, so
  the test's fixed path is a narrow, independently correctable seam. The
  database default remains a separate follow-up boundary and is not included
  in the first slice.

## Recommended first acceptance task

Create and implement one Axiom issue: make
`tests/test_bootstrap_check_cli.py` derive `ROOT` from its own path and derive
`BOOTSTRAP_CHECK` from that root. Keep the expected command output unchanged.

This is a one-file, low-risk foundation change: it strengthens the meaning of
the test when run from a disposable worktree without changing AXIOM runtime
authority, database configuration, governance records, or production
behavior.

Acceptance command:

```powershell
python -m pytest tests/test_bootstrap_check_cli.py -q
```

The task must be rejected if it expands into changing the default database
location, enabling runtime facilities, or altering bootstrap pass/fail rules.

## Deferred candidates

- Make remaining hard-coded repository/database paths configurable: broader
  and needs an explicit isolation and persistence design.
- Separate repair from `tools/verify_foundation.py`: potentially valuable but
  changes verification semantics and needs dedicated scope.
- Any gateway, scheduler, IPC, or autonomy work: outside the first acceptance
  boundary.
