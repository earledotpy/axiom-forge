# Adapter Evidence Register

## Evidence Record Format

Every future `record.json` uses schema version 2 and includes these CLI
provenance fields. A real CLI adapter writes them after resolving its CLI and
before it invokes that CLI:

- `cli_command`: command name the adapter invoked;
- `cli_path`: resolved executable path; and
- `cli_version`: first non-empty line from a best-effort `--version` call, or
  `null` when that call cannot yield a version.

When an adapter does not invoke a CLI, all three fields are `null`. If its CLI
is absent, it fails closed and the run remains `FAILED`; it does not fabricate
provenance.

Future evidence for a real CLI adapter must also record:

- collection timestamp;
- adapter name and adapter script;
- the captured `cli_command`, `cli_path`, and `cli_version` values;
- run ID and base SHA;
- verification result;
- promotion result and identifiers, or the exact failed-closed reason; and
- concise outcome summary.

CLI availability and version observations are not proof of adapter safety or
trust. Recording this format does not automatically change an adapter's status
or trust level. Existing historical entries must not be treated as containing a
version captured at the exact run time unless they explicitly say so.

Antigravity remains experimental unless separately reviewed and approved
through future evidence and an explicit human decision.

## Mandate 21 — Codex Full Loop

Status: PASS

- Adapter: codex
- Run ID: 20260617-064342-835144
- Base SHA: daf7115f550d56e9ab8378e4ae18e8218384dff5
- Gate branch: gate/20260617-064342-835144
- Promotion commit: ee35ef16c8eb3c7eb4309c8672d4817e713ca573
- Result: Codex-produced patch verified from scratch and promoted.
- Diff summary: `app/target.py` changed `return "base"` to `return "codex-promoted"`.

## Mandate 22 — Claude Code Full Loop

Status: PASS

- Adapter: claude-code
- Run ID: 20260617-070238-253720
- Base SHA: daf7115f550d56e9ab8378e4ae18e8218384dff5
- Gate branch: gate/20260617-070238-253720
- Promotion commit: 5c0a8e53c2852b512689808147ad11923dbd69ff
- Result: Claude Code-produced patch verified from scratch and promoted.
- Diff summary: `app/target.py` changed `return "base"` to `return "claude-promoted"`.

## Mandate 23 — Antigravity Hardened Retest

Status: FAIL_CLOSED_EXPECTED

- Adapter: antigravity
- Run ID: 20260617-072537-634380
- Base SHA: daf7115f550d56e9ab8378e4ae18e8218384dff5
- Failure: `patch_check_failed`
- Detail: `patch.diff` added a blank line at EOF / whitespace error.
- Result: Not promoted.
- Decision: Antigravity remains experimental until it repeatedly produces whitespace-clean patches under the hardened gate.

## Final Health Check

Status: PASS

- Promotion matrix: PASS, 13 passed / 0 failed
- Runner matrix: PASS, 13 passed / 0 failed
- Overall: `AXIOM_FORGE_CHECK: PASS`
