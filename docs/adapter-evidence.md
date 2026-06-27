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

## Copilot Qualification — 2026-06-25

Status: QUALIFIED

- Adapter: copilot
- Qualification configuration: `agents/copilot.sh` revision `3cb9c5c8c96924d30b87f5c62666f97c3ed2d1c0`; GitHub Copilot CLI 1.0.64 at `C:\Users\jerem\AppData\Local\Microsoft\WinGet\Packages\GitHub.Copilot_Microsoft.Winget.Source_8wekyb3d8bbwe\copilot.exe`; model `GitHub Copilot CLI default`; restricted `view,create,edit` tool allow-list with write permission, supplied-worktree directory mode, temporary directory access disabled, built-in MCPs disabled, remote sessions/export disabled, auto-update disabled, and isolated-worktree prompt protocol.
- Base SHA: `23e54babeafbbac6504755e0dab8f2019ec98e36`
- Result: one contiguous successful series with no resets. Raw run artifacts remain local under `runs/` and are not committed.

| Case | Run ID | Task specification | Allowed-path specification | Acceptance specification | Patch SHA-256 | Scope | Acceptance |
| --- | --- | --- | --- | --- | --- | --- | --- |
| behavior-change | `20260625-055149-912826` | `qualification/cases/behavior-change/task.md` `2cf8c1820f825e1cca6944fa139a6127464e0dc15b707454db1e8abb8da0cb6d` | `qualification/cases/behavior-change/allowed-paths.txt` `13c75990a8144aaf76db6ed595dd58bab3ffb155ec88e870e3ea8399f9550ec1` | `qualification/cases/behavior-change/accept.sh` `9d423644b8ac1b624c4f67137d8d9cbbe1963f5911ec2802d908449c26988493` | `74a27b646a99450d85b90f7c1f23cb6d401524249b37ec6a1b51cd7110cf8382` | PASS | PASS |
| new-behavior | `20260625-055217-100581` | `qualification/cases/new-behavior/task.md` `31a924690d3bf8b784c88efb6d52fe29ee5177c3c1a67b2b0c4ba3bed11f8a9d` | `qualification/cases/new-behavior/allowed-paths.txt` `13c75990a8144aaf76db6ed595dd58bab3ffb155ec88e870e3ea8399f9550ec1` | `qualification/cases/new-behavior/accept.sh` `94912bc05d2b7df59dfb588e1f6e9f3a454b143aa54fb796e47b8c41f36792aa` | `0c5e0284ea0fd7c19f74bd62d5a6143bca4f7331ed5b6ee152db8b2056e964fe` | PASS | PASS |
| edge-case | `20260625-055251-256003` | `qualification/cases/edge-case/task.md` `c03f25d4e9c6b0125491b622c705f689804da55f061e10c08784fb9be27cd795` | `qualification/cases/edge-case/allowed-paths.txt` `13c75990a8144aaf76db6ed595dd58bab3ffb155ec88e870e3ea8399f9550ec1` | `qualification/cases/edge-case/accept.sh` `7e03a8f6361b3d31f6a9668fee9af6a08c4b1e2e19d371d0d1c77b19e71f600e` | `0df6405df60c37a71bcc0d9af1511941890e37cd002595c410eeb0de17e02bb4` | PASS | PASS |

Decision: Copilot is `stable` with `standard` trust for this configuration.
Any adapter-script, CLI-version, selected-model, or relevant-configuration
drift invalidates that status until a new qualification series succeeds.

## OpenCode Qualification — 2026-06-25

Status: QUALIFIED

- Adapter: opencode
- Qualification configuration: `agents/opencode.sh` revision `6c0625dee3862623f9cf9892a2d678ee4bd9e0b3`; OpenCode 1.17.10 at `C:\Users\jerem\.opencode\bin\opencode.exe`; model `OpenCode default`; `opencode run --dir` supplied-worktree mode with `build` agent, JSON output, `--pure`, runtime `OPENCODE_CONFIG_CONTENT` permission override, read/glob/grep/edit/write enabled, bash/task/webfetch/websearch/question disabled, external directories denied, no dangerous permission bypass, and isolated-worktree prompt protocol.
- Base SHA: `499eaa7b50c931da3e80cd6a56ec2750777e4cb6`
- Result: one contiguous successful series with no resets after the path-resolution fix commit. Raw run artifacts remain local under `runs/` and are not committed.

| Case | Run ID | Task specification | Allowed-path specification | Acceptance specification | Patch SHA-256 | Scope | Acceptance |
| --- | --- | --- | --- | --- | --- | --- | --- |
| behavior-change | `20260625-171249-967828` | `qualification/cases/behavior-change/task.md` `2cf8c1820f825e1cca6944fa139a6127464e0dc15b707454db1e8abb8da0cb6d` | `qualification/cases/behavior-change/allowed-paths.txt` `13c75990a8144aaf76db6ed595dd58bab3ffb155ec88e870e3ea8399f9550ec1` | `qualification/cases/behavior-change/accept.sh` `9d423644b8ac1b624c4f67137d8d9cbbe1963f5911ec2802d908449c26988493` | `74a27b646a99450d85b90f7c1f23cb6d401524249b37ec6a1b51cd7110cf8382` | PASS | PASS |
| new-behavior | `20260625-171416-746141` | `qualification/cases/new-behavior/task.md` `31a924690d3bf8b784c88efb6d52fe29ee5177c3c1a67b2b0c4ba3bed11f8a9d` | `qualification/cases/new-behavior/allowed-paths.txt` `13c75990a8144aaf76db6ed595dd58bab3ffb155ec88e870e3ea8399f9550ec1` | `qualification/cases/new-behavior/accept.sh` `94912bc05d2b7df59dfb588e1f6e9f3a454b143aa54fb796e47b8c41f36792aa` | `10c89412b94ede7a7aa7d459040f62f0cc140d5eea7813aea0a3d536cd033461` | PASS | PASS |
| edge-case | `20260625-171519-722917` | `qualification/cases/edge-case/task.md` `c03f25d4e9c6b0125491b622c705f689804da55f061e10c08784fb9be27cd795` | `qualification/cases/edge-case/allowed-paths.txt` `13c75990a8144aaf76db6ed595dd58bab3ffb155ec88e870e3ea8399f9550ec1` | `qualification/cases/edge-case/accept.sh` `7e03a8f6361b3d31f6a9668fee9af6a08c4b1e2e19d371d0d1c77b19e71f600e` | `a6d8d2962ca235ab53a9e734528745fbadd1aad2ad7f54890dbe5e367f5a39dc` | PASS | PASS |

Decision: OpenCode is `stable` with `standard` trust for this configuration.
Any adapter-script, CLI-version, selected-model, or relevant-configuration
drift invalidates that status until a new qualification series succeeds.

## Cursor Qualification — 2026-06-25

Status: QUALIFIED

- Adapter: cursor
- Qualification configuration: `agents/cursor.sh` revision `864192a924cf573680157a4b3b8e216acf72a6a2`; Cursor Agent `2026.06.24-00-45-58-9f61de7` at `C:\Users\jerem\AppData\Local\cursor-agent\cursor-agent.cmd`; model `Cursor Agent default`; `--print --force --workspace` supplied-worktree mode; JSON output; `--sandbox disabled` because Cursor reports sandbox mode is unavailable on Windows; runtime `.cursor/cli.json` project permission allowlist, read/write enabled, shell/env-file/MCP/web fetch access denied, and isolated-worktree prompt protocol.
- Base SHA: `62c7e6847f587c6d892e25ca0fa6cd3a20ae6d9b`
- Result: one contiguous successful series with no resets after the prompt-delivery fix commit. Raw run artifacts remain local under `runs/` and are not committed.

| Case | Run ID | Task specification | Allowed-path specification | Acceptance specification | Patch SHA-256 | Scope | Acceptance |
| --- | --- | --- | --- | --- | --- | --- | --- |
| behavior-change | `20260626-041535-846879` | `qualification/cases/behavior-change/task.md` `2cf8c1820f825e1cca6944fa139a6127464e0dc15b707454db1e8abb8da0cb6d` | `qualification/cases/behavior-change/allowed-paths.txt` `13c75990a8144aaf76db6ed595dd58bab3ffb155ec88e870e3ea8399f9550ec1` | `qualification/cases/behavior-change/accept.sh` `9d423644b8ac1b624c4f67137d8d9cbbe1963f5911ec2802d908449c26988493` | `74a27b646a99450d85b90f7c1f23cb6d401524249b37ec6a1b51cd7110cf8382` | PASS | PASS |
| new-behavior | `20260626-041616-399402` | `qualification/cases/new-behavior/task.md` `31a924690d3bf8b784c88efb6d52fe29ee5177c3c1a67b2b0c4ba3bed11f8a9d` | `qualification/cases/new-behavior/allowed-paths.txt` `13c75990a8144aaf76db6ed595dd58bab3ffb155ec88e870e3ea8399f9550ec1` | `qualification/cases/new-behavior/accept.sh` `94912bc05d2b7df59dfb588e1f6e9f3a454b143aa54fb796e47b8c41f36792aa` | `10c89412b94ede7a7aa7d459040f62f0cc140d5eea7813aea0a3d536cd033461` | PASS | PASS |
| edge-case | `20260626-041658-791972` | `qualification/cases/edge-case/task.md` `c03f25d4e9c6b0125491b622c705f689804da55f061e10c08784fb9be27cd795` | `qualification/cases/edge-case/allowed-paths.txt` `13c75990a8144aaf76db6ed595dd58bab3ffb155ec88e870e3ea8399f9550ec1` | `qualification/cases/edge-case/accept.sh` `7e03a8f6361b3d31f6a9668fee9af6a08c4b1e2e19d371d0d1c77b19e71f600e` | `704219299e7d21fe2f0aad73055bca0f9b3bc631586af73b310357e983513994` | PASS | PASS |

Decision: Cursor is `stable` with `standard` trust for this configuration.
Any adapter-script, CLI-version, selected-model, or relevant-configuration
drift invalidates that status until a new qualification series succeeds.

## Kiro Feasibility Probe — 2026-06-26

Status: PASS_EXPERIMENTAL

- Adapter: kiro
- Probe scope: temp-clone real-task probe only; not a standard-adapter qualification series.
- Probe run ID: `20260626-065258-212079`
- Probe base SHA: `e2f3940c3508e83d5643d3f2f71e114052fc8328` in temp clone `C:\Users\jerem\AppData\Local\Temp\axiom-forge-kiro-probe-clone-dfe4e245-b531-40d8-99e2-e20c4103b053`
- CLI provenance: `kiro-cli.exe`; `C:\Users\jerem\AppData\Local\Kiro-Cli\kiro-cli.exe`; `kiro-cli-chat 2.10.0`
- Result: `scripts/run_agent_task.sh kiro tasks/change-answer.task.md` completed, `scripts/validate_run_dir.sh` accepted the run directory, and `scripts/verify_patch.sh` passed from a disposable verifier worktree.
- Diff summary: `app/target.py` changed `return "base"` to `return "runner-promoted"`.
- Decision: Kiro remains `experimental` with `experimental` trust. Standard trust requires a clean contiguous three-case qualification series and a separate docs/status update.

## Kiro Qualification — 2026-06-26

Status: QUALIFIED

- Adapter: kiro
- Qualification configuration: `agents/kiro.sh` revision `3cbedf56b483472cc77ceccec848c6c8d19efc8f`; Kiro CLI `kiro-cli-chat 2.10.0` at `C:\Users\jerem\AppData\Local\Kiro-Cli\kiro-cli.exe`; model `Kiro CLI default`; `kiro-cli.exe chat --no-interactive` from the supplied worktree, `--trust-tools=read,write`, no `--trust-all-tools`, task copied into `.kiro/axiom-task.md`, and isolated-worktree prompt protocol.
- Base SHA: `361b86544b9e28cba5a43136bf81147d95a5914d`
- Result: one contiguous successful series with no resets. Raw run artifacts remain local under the clean temp clone's `runs/` directory and are not committed.

| Case | Run ID | Task specification | Allowed-path specification | Acceptance specification | Patch SHA-256 | Scope | Acceptance |
| --- | --- | --- | --- | --- | --- | --- | --- |
| behavior-change | `20260626-065713-161584` | `qualification/cases/behavior-change/task.md` `70c15be43693ef7fee09f26582d4cd4bf5a9dc14d9fe2a1dfd5c02117d9362ac` | `qualification/cases/behavior-change/allowed-paths.txt` `d92c733e99997fa547562ff5118c5233af8b0a8234bb021bb0999b147dd4001e` | `qualification/cases/behavior-change/accept.sh` `f034e780220a979e8b8a05c42df47bb67c0b002f60eaae343c997860b3ab1462` | `74a27b646a99450d85b90f7c1f23cb6d401524249b37ec6a1b51cd7110cf8382` | PASS | PASS |
| new-behavior | `20260626-065737-694509` | `qualification/cases/new-behavior/task.md` `3f539a7903a0d1fa299094847c841ae07ac6dfe2c0bddee7fde471a2fc09cdee` | `qualification/cases/new-behavior/allowed-paths.txt` `d92c733e99997fa547562ff5118c5233af8b0a8234bb021bb0999b147dd4001e` | `qualification/cases/new-behavior/accept.sh` `afbb786392cb439deaf38891ec40b698cc03deb97acd65f9a4e68e3c2ecf6d1d` | `acea5d0c4f0d02ee9c58f985d3d5f4ba97ce1a50e4663cf11bafcf178d6a0148` | PASS | PASS |
| edge-case | `20260626-065804-591313` | `qualification/cases/edge-case/task.md` `26ff542ee38f29deb3baa853dd9f23ee3497bb5980a60d472d5c9cc395eedfe5` | `qualification/cases/edge-case/allowed-paths.txt` `d92c733e99997fa547562ff5118c5233af8b0a8234bb021bb0999b147dd4001e` | `qualification/cases/edge-case/accept.sh` `68088ba7274de1808ab4991925d71d6aa0cefb4525674f9bba9327fa8d9be540` | `e2b212d8191271af7d274b98bbfb80a05783c5478f054f02f07940b44e6cd125` | PASS | PASS |

Decision: Kiro is `stable` with `standard` trust for this configuration.
Any adapter-script, CLI-version, selected-model, or relevant-configuration
drift invalidates that status until a new qualification series succeeds.

## QoderCLI Marker Probe — 2026-06-26

Status: PASS_EXPERIMENTAL

- Adapter: qoder
- Probe scope: disposable marker-file probe only; not a captured Axiom Forge
  run and not a standard-adapter qualification series.
- Probe directory: `C:\Users\jerem\AppData\Local\Temp\axiom-forge-qodercli-marker-04dad0ac-cb5e-4dfc-8a51-9bd9b024b449`
- CLI observation: `qodercli-1.0.30.exe --version` reported `1.0.30`; Git
  Bash can resolve `qodercli-1.0.30.exe` after prepending
  `/c/Users/jerem/.qoder/bin/qodercli` to `PATH`.
- Result: `qodercli-1.0.30.exe -p --cwd <probe-dir> --permission-mode
  accept_edits` with restricted `Read`, `Write`, `Edit`, `Grep`, and `Glob`
  tools created `marker.txt` with exact content `READY`.
- Decision: QoderCLI remains `experimental` with `experimental` trust.
  Standard trust requires a clean contiguous three-case qualification series
  and a separate docs/status update.

## QoderCLI Feasibility Probe — 2026-06-26

Status: PASS_EXPERIMENTAL

- Adapter: qoder
- Probe scope: temp-clone real-task probe only; not a standard-adapter
  qualification series.
- Probe run ID: `20260626-072029-621627`
- Probe base SHA: `48c4ae0f8276994d45023c25cfcf965433492099` in temp clone
  `C:\Users\jerem\AppData\Local\Temp\axiom-forge-qodercli-probe-clone-afbabdc8-557a-41de-9eb6-6b605e106421`
- CLI provenance: `qodercli-1.0.30.exe`;
  `C:\Users\jerem\.qoder\bin\qodercli\qodercli-1.0.30.exe`; `1.0.30`
- Result: `scripts/run_agent_task.sh qoder tasks/change-answer.task.md`
  completed, `scripts/validate_run_dir.sh` accepted the run directory, and
  `scripts/verify_patch.sh` passed from a disposable verifier worktree.
- Diff summary: `app/target.py` changed `return "base"` to
  `return "runner-promoted"`.
- Decision: QoderCLI remains `experimental` with `experimental` trust.
  Standard trust requires a clean contiguous three-case qualification series
  and a separate docs/status update.

## QoderCLI Qualification — 2026-06-26

Status: QUALIFIED

- Adapter: qoder
- Qualification configuration: `agents/qoder.sh` revision
  `00d55293770be7ece9505f17e50cf3797662cbfa`; QoderCLI `1.0.30` at
  `C:\Users\jerem\.qoder\bin\qodercli\qodercli-1.0.30.exe`; model
  `QoderCLI default`; `qodercli-1.0.30.exe --print --cwd <supplied-worktree>
  --permission-mode accept_edits`; restricted `Read`, `Write`, `Edit`, `Grep`,
  and `Glob` tools; denied shell, web, agent, MCP, and question tools; empty
  strict MCP config; no dangerous permission bypass, remote mode, worktree
  creation, or extra directory; task copied into `.qoder/axiom-task.md`; and
  isolated-worktree prompt protocol.
- Base SHA: `71f6d8e3dd3c2648570ab95deee843c33570bcbb`
- Result: one contiguous successful series with no resets. Raw run artifacts
  remain local under the clean temp clone's `runs/` directory and are not
  committed.

| Case | Run ID | Task specification | Allowed-path specification | Acceptance specification | Patch SHA-256 | Scope | Acceptance |
| --- | --- | --- | --- | --- | --- | --- | --- |
| behavior-change | `20260626-072456-126451` | `qualification/cases/behavior-change/task.md` `70c15be43693ef7fee09f26582d4cd4bf5a9dc14d9fe2a1dfd5c02117d9362ac` | `qualification/cases/behavior-change/allowed-paths.txt` `d92c733e99997fa547562ff5118c5233af8b0a8234bb021bb0999b147dd4001e` | `qualification/cases/behavior-change/accept.sh` `f034e780220a979e8b8a05c42df47bb67c0b002f60eaae343c997860b3ab1462` | `74a27b646a99450d85b90f7c1f23cb6d401524249b37ec6a1b51cd7110cf8382` | PASS | PASS |
| new-behavior | `20260626-072529-871366` | `qualification/cases/new-behavior/task.md` `3f539a7903a0d1fa299094847c841ae07ac6dfe2c0bddee7fde471a2fc09cdee` | `qualification/cases/new-behavior/allowed-paths.txt` `d92c733e99997fa547562ff5118c5233af8b0a8234bb021bb0999b147dd4001e` | `qualification/cases/new-behavior/accept.sh` `afbb786392cb439deaf38891ec40b698cc03deb97acd65f9a4e68e3c2ecf6d1d` | `10c89412b94ede7a7aa7d459040f62f0cc140d5eea7813aea0a3d536cd033461` | PASS | PASS |
| edge-case | `20260626-072605-561112` | `qualification/cases/edge-case/task.md` `26ff542ee38f29deb3baa853dd9f23ee3497bb5980a60d472d5c9cc395eedfe5` | `qualification/cases/edge-case/allowed-paths.txt` `d92c733e99997fa547562ff5118c5233af8b0a8234bb021bb0999b147dd4001e` | `qualification/cases/edge-case/accept.sh` `68088ba7274de1808ab4991925d71d6aa0cefb4525674f9bba9327fa8d9be540` | `ef4413d1ecb6823641eb8fdb293920d144b0ab63b42a1475d0ea8f9df496dbfb` | PASS | PASS |

Decision: QoderCLI is `stable` with `standard` trust for this configuration.
Any adapter-script, CLI-version, selected-model, or relevant-configuration
drift invalidates that status until a new qualification series succeeds.

## Kilo Marker and Feasibility Probes — 2026-06-27

Status: PASS_EXPERIMENTAL

- Adapter: kilo
- Probe scope: disposable marker-file probe, shell-denial probe, and
  temp-clone real-task probe only; not a standard-adapter qualification series.
- Marker probe directory:
  `C:\Users\jerem\AppData\Local\Temp\axiom-forge-kilo-marker-b84ab941-b78f-47e0-92c9-879401d5f0b7`
- Shell-denial probe directory:
  `C:\Users\jerem\AppData\Local\Temp\axiom-forge-kilo-shell-denial-d2acddef-cde3-4471-9b28-424774fd027e`
- CLI observation: local npm package `@kilocode/cli@7.3.54`; PowerShell and
  Git Bash can resolve `kilo` and `kilocode` under
  `C:\Users\jerem\.npm-global`; `kilo --version` reported `7.3.54`.
- Boundary tested: `kilo run --dir <probe-dir> --agent axiom-forge-probe
  --format json --pure --auto` with a project-local primary agent allowing
  read, edit, write, glob, and grep while denying bash, web fetch/search,
  task/subagent, skill, LSP, and external-directory tools. The dangerous
  `--dangerously-skip-permissions` flag was not used.
- Marker result: Kilo created only `marker.txt` with exact content `READY`
  plus its project-local `.kilo/` support files.
- Shell-denial result: when asked to create `shell-created.txt` with a shell
  command, Kilo reported no shell/bash/terminal command tool was available and
  `shell-created.txt` was not created.
- Temp-clone probe run ID: `20260627-155820-915057`
- Probe base SHA: `f1a7ce3326b5785b49ccaa5ae9a01e4673c6b184` in temp clone
  `C:\Users\jerem\AppData\Local\Temp\axiom-forge-kilo-probe-clone-eb69b2b5-8fba-45b4-b14f-87ddc17b3e7d`
- CLI provenance: `kilo`; `C:\Users\jerem\.npm-global\kilo.cmd`; `7.3.54`
- Result: `scripts/run_agent_task.sh kilo tasks/change-answer.task.md`
  completed, `scripts/validate_run_dir.sh` accepted the run directory, and
  `scripts/verify_patch.sh` passed from a disposable verifier worktree.
- Diff summary: `app/target.py` changed `return "base"` to
  `return "runner-promoted"`.
- Decision: Kilo remains `experimental` with `experimental` trust. Standard
  trust requires a clean contiguous three-case qualification series and a
  separate docs/status update.

## Kilo Qualification — 2026-06-27

Status: QUALIFIED

- Adapter: kilo
- Qualification configuration: `agents/kilo.sh` revision
  `18daf97384b1329aa3681f1fa8de4923df47dd57`; Kilo CLI `7.3.54` at
  `C:\Users\jerem\.npm-global\kilo.cmd`; model `Kilo default`; `kilo run
  --dir <supplied-worktree> --format json --pure --auto` with a project-local
  primary agent; read/edit/write/glob/grep allowed; bash, web fetch/search,
  task/subagent, skill, LSP, external-directory, and todo tools denied; no
  `--dangerously-skip-permissions`, attach, serve, web, remote, daemon, or
  cloud-fork modes; task copied into `.kilo/axiom-task.md`; and
  isolated-worktree prompt protocol.
- Base SHA: `ed2c9f4890253a8cda16640ecfd3d9558096caf9`
- Result: one contiguous successful series with no resets after the
  qualification metadata fix commit. Raw run artifacts remain local under the
  clean temp clone's `runs/` directory and are not committed.

| Case | Run ID | Task specification | Allowed-path specification | Acceptance specification | Patch SHA-256 | Scope | Acceptance |
| --- | --- | --- | --- | --- | --- | --- | --- |
| behavior-change | `20260627-160406-688609` | `qualification/cases/behavior-change/task.md` `70c15be43693ef7fee09f26582d4cd4bf5a9dc14d9fe2a1dfd5c02117d9362ac` | `qualification/cases/behavior-change/allowed-paths.txt` `d92c733e99997fa547562ff5118c5233af8b0a8234bb021bb0999b147dd4001e` | `qualification/cases/behavior-change/accept.sh` `f034e780220a979e8b8a05c42df47bb67c0b002f60eaae343c997860b3ab1462` | `74a27b646a99450d85b90f7c1f23cb6d401524249b37ec6a1b51cd7110cf8382` | PASS | PASS |
| new-behavior | `20260627-160445-851182` | `qualification/cases/new-behavior/task.md` `3f539a7903a0d1fa299094847c841ae07ac6dfe2c0bddee7fde471a2fc09cdee` | `qualification/cases/new-behavior/allowed-paths.txt` `d92c733e99997fa547562ff5118c5233af8b0a8234bb021bb0999b147dd4001e` | `qualification/cases/new-behavior/accept.sh` `afbb786392cb439deaf38891ec40b698cc03deb97acd65f9a4e68e3c2ecf6d1d` | `acea5d0c4f0d02ee9c58f985d3d5f4ba97ce1a50e4663cf11bafcf178d6a0148` | PASS | PASS |
| edge-case | `20260627-160534-211007` | `qualification/cases/edge-case/task.md` `26ff542ee38f29deb3baa853dd9f23ee3497bb5980a60d472d5c9cc395eedfe5` | `qualification/cases/edge-case/allowed-paths.txt` `d92c733e99997fa547562ff5118c5233af8b0a8234bb021bb0999b147dd4001e` | `qualification/cases/edge-case/accept.sh` `68088ba7274de1808ab4991925d71d6aa0cefb4525674f9bba9327fa8d9be540` | `30f31d969a3da7abf34cd78bc7ffea1167790ffddd605a659016d57affdde5f8` | PASS | PASS |

Decision: Kilo is `stable` with `standard` trust for this configuration. Any
adapter-script, CLI-version, selected-model, or relevant-configuration drift
invalidates that status until a new qualification series succeeds.

## Cline Marker Probe — 2026-06-26

Status: PASS_EXPERIMENTAL

- Candidate: cline
- Probe scope: disposable marker-file probe only; not a captured Axiom Forge
  run and not a standard-adapter qualification series.
- Probe directory:
  `C:\Users\jerem\AppData\Local\Temp\axiom-forge-cline-marker-51d587c6-06e3-4999-90a9-801a9ccc49f0`
- CLI observation: local npm package `cline` version `3.0.30`; Git Bash can
  resolve `cline` after prepending `/c/Users/jerem/.npm-global` to `PATH`.
- Result: `cline --cwd <probe-dir> --json --auto-approve true --timeout 180`
  with an attempted `CLINE_COMMAND_PERMISSIONS` shell-command denial setting
  created only `marker.txt` with exact content `READY`; this marker probe did
  not prove the denial setting.
- Follow-up runner probe: temp-clone runs `20260626-075441-547304` and
  `20260626-080058-331527` both failed with `agent_execution_failed`. The
  second log showed Cline invoking `run_commands` despite the adapter setting
  `CLINE_COMMAND_PERMISSIONS` to deny all shell commands.
- Decision: Cline is `blocked` for adapter registration. Do not add a runnable
  adapter until current first-party evidence or a new controlled probe proves
  shell-command denial and clean task completion under the Axiom Forge adapter
  contract.

## Final Health Check

Status: PASS

- Adapter CLI preflight: PASS, including required `cursor-agent.cmd`,
  `kiro-cli.exe`, and `qodercli-1.0.30.exe`
- Final clean-clone proof: `AXIOM_FORGE_CHECK: PASS` after QoderCLI standard promotion
- Gate contract matrix: PASS
- Promotion matrix: PASS, 20 passed / 0 failed
- Runner matrix: PASS, 15 passed / 0 failed
- Qualification matrix: PASS
- Qualification series matrix: PASS
- Overall: `AXIOM_FORGE_CHECK: PASS`
