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

Antigravity's current standard status is recorded below. It remains valid only
for the pinned qualification configuration.

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

## Antigravity Qualification — 2026-06-24

Status: QUALIFIED

- Adapter: antigravity
- Qualification configuration: `agents/antigravity.sh` revision `14c406033d2514e5e443af3cebfe8e315903c466`; `agy` 1.0.11 at `C:\Users\jerem\AppData\Local\agy\bin\agy.exe`; model `Gemini 3.5 Flash (Low)`; print-mode isolated-worktree prompt protocol.
- Base SHA: `54e283ce178a5d0c2cc8f4b71af52558f4ed420a`
- Result: one contiguous successful series with no resets. Raw run artifacts remain local under `runs/` and are not committed.

| Case | Run ID | Task specification | Allowed-path specification | Acceptance specification | Patch SHA-256 | Scope | Acceptance |
| --- | --- | --- | --- | --- | --- | --- | --- |
| behavior-change | `20260624-144415-988783` | `qualification/cases/behavior-change/task.md` `70c15be43693ef7fee09f26582d4cd4bf5a9dc14d9fe2a1dfd5c02117d9362ac` | `qualification/cases/behavior-change/allowed-paths.txt` `d92c733e99997fa547562ff5118c5233af8b0a8234bb021bb0999b147dd4001e` | `qualification/cases/behavior-change/accept.sh` `f034e780220a979e8b8a05c42df47bb67c0b002f60eaae343c997860b3ab1462` | `74a27b646a99450d85b90f7c1f23cb6d401524249b37ec6a1b51cd7110cf8382` | PASS | PASS |
| new-behavior | `20260624-144447-034723` | `qualification/cases/new-behavior/task.md` `3f539a7903a0d1fa299094847c841ae07ac6dfe2c0bddee7fde471a2fc09cdee` | `qualification/cases/new-behavior/allowed-paths.txt` `d92c733e99997fa547562ff5118c5233af8b0a8234bb021bb0999b147dd4001e` | `qualification/cases/new-behavior/accept.sh` `afbb786392cb439deaf38891ec40b698cc03deb97acd65f9a4e68e3c2ecf6d1d` | `10c89412b94ede7a7aa7d459040f62f0cc140d5eea7813aea0a3d536cd033461` | PASS | PASS |
| edge-case | `20260624-144512-961551` | `qualification/cases/edge-case/task.md` `26ff542ee38f29deb3baa853dd9f23ee3497bb5980a60d472d5c9cc395eedfe5` | `qualification/cases/edge-case/allowed-paths.txt` `d92c733e99997fa547562ff5118c5233af8b0a8234bb021bb0999b147dd4001e` | `qualification/cases/edge-case/accept.sh` `68088ba7274de1808ab4991925d71d6aa0cefb4525674f9bba9327fa8d9be540` | `a6d8d2962ca235ab53a9e734528745fbadd1aad2ad7f54890dbe5e367f5a39dc` | PASS | PASS |

Decision: Antigravity is `stable` with `standard` trust for this configuration.
Any adapter-script, CLI-version, selected-model, or relevant-configuration
drift invalidates that status until a new qualification series succeeds.

## Final Health Check

Status: PASS

- Promotion matrix: PASS, 13 passed / 0 failed
- Runner matrix: PASS, 13 passed / 0 failed
- Overall: `AXIOM_FORGE_CHECK: PASS`
