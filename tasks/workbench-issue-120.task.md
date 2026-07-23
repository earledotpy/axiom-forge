<!-- axiom-forge-workbench-approved-adapter: codex -->
Implement Issue #120: Replace native confirm/prompt dialogs with in-page dialogs

Planning source: https://github.com/earledotpy/axiom-forge/issues/120

Task intent:
Replace native confirm/prompt dialogs with in-page dialogs: The Execute confirmation and the Promote run-ID attestation become in-page dialog elements instead of native `window.confirm` / `window.prompt`. The attestation semantics are unchanged: promotion still requires the operator to type the exact run ID, and execution still requires an explicit confirm. Only the dialog mechanism changes.

Constraints:
- Keep the patch bounded to the approved target task scope.
- Do not change promotion behavior.
- Do not create run evidence until the operator approves delegation.
