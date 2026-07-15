<!-- axiom-forge-workbench-approved-adapter: codex -->
Implement Issue #2: Make the bootstrap CLI integration test worktree-relative

Planning source: https://github.com/earledotpy/axiom/issues/2

Task intent:
Make the bootstrap CLI integration test worktree-relative: Replace the fixed `C:\\axiom` root in `tests/test_bootstrap_check_cli.py` with a root derived from the test file's location, so the test invokes `tools/bootstrap_check.py` from the checkout being tested.

Constraints:
- Keep the patch bounded to the approved target task scope.
- Do not change promotion behavior.
- Do not create run evidence until the operator approves delegation.
