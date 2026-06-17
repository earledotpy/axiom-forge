# Adapter Evidence Register

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
- Runner matrix: PASS, 7 passed / 0 failed
- Overall: `AXIOM_FORGE_CHECK: PASS`