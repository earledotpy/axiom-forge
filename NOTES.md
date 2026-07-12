# Workflow Notes

## Canonical loops

- Axiom Forge issue to committed implementation: a repeated repo loop where an issue or PRD becomes a bounded implementation slice, is validated, committed, and reported.

## Canonical triggers

- `@implement Issue #N`: explicit event trigger for the Axiom Forge issue to committed implementation workflow.

## Source of truth

- Live GitHub issue text is authoritative for `@implement Issue #N` runs; pasted or summarized issue text is context only. If live issue fetch fails, the workflow stops before editing.

## Tools and channels

- Repository: `C:\axiom-forge`
- Issue tracker: GitHub Issues
- Local shell: PowerShell on Windows, with Bash scripts used for project validation