# Adapter Evaluation Decision Map

Issue #15 separates current adapter evaluation behavior into three decisions:

- lightweight candidate adapter compatibility;
- `standard` adapter trust; and
- normal captured-run / verified-patch workflow behavior.

This map is descriptive only. It does not change operator-facing commands,
registered adapter status, trust policy, qualification evidence, or promotion
behavior.

## Decision Categories

| Category | Decision it supports | What it can prove | What it must not imply |
| --- | --- | --- | --- |
| Candidate compatibility | Whether a candidate CLI can plausibly function through Axiom Forge's adapter interface. | The CLI can be resolved, invoked from the expected shell context, constrained to a supplied worktree well enough for a bounded probe, and produce a captured run that can be validated and verified. | `standard` trust, adapter registration, qualification, promotion approval, or future reliability. |
| Standard trust | Whether a registered adapter configuration is suitable for normal local Axiom Forge use. | The pinned adapter script, CLI version, selected model, and relevant configuration completed the full contiguous three-case qualification series. | General trust in a product name, a changed CLI/configuration, or any unqualified future adapter revision. |
| Captured-run / verified-patch workflow | Whether one captured run produced a valid patch that can be verified and, with operator approval, promoted. | The run directory and patch satisfy the core gate contracts for that single captured run. | Adapter-wide compatibility, standard trust, or approval to promote without the explicit promotion flow. |

## Source-Backed Behavior Map

| Current behavior | Source | Category | Classification |
| --- | --- | --- | --- |
| Adapter scripts expose `agents/<adapter>.sh <task_file> <worktree>`. | `docs/adapters.md`; `README.md`; `scripts/run_agent_task.sh` | Candidate compatibility; captured-run workflow | Necessary compatibility surface because every candidate must fit the runner's invocation shape. It is also the normal runner entrypoint for captured runs. |
| The runner requires a clean target checkout before a run. | `scripts/run_agent_task.sh` | Captured-run workflow | Core gate behavior. It protects run evidence and is not unique to candidate compatibility or standard trust. |
| The runner creates a detached disposable worktree, invokes the adapter, captures logs, captures a patch, and writes `record.json`. | `scripts/run_agent_task.sh`; `README.md`; `docs/adr/0002-captured-run-record-module.md` | Captured-run workflow; candidate compatibility | A successful candidate compatibility probe should exercise this path because it proves the CLI can operate through Axiom Forge's real capture mechanism. |
| The runner fails closed if the adapter changes `HEAD`, leaves detached `HEAD`, creates or deletes branches, modifies the target checkout, exits non-zero, or produces an empty patch. | `scripts/run_agent_task.sh`; `docs/adapters.md`; `README.md` | Captured-run workflow; candidate compatibility; standard trust | These checks are core run safety. A candidate must pass them to show basic compatibility, and every qualification case depends on them for trust. |
| Real CLI adapters must record `cli_command`, `cli_path`, and `cli_version`; missing or invalid provenance fails closed. | `scripts/run_agent_task.sh`; `scripts/adapter_identity.py`; `docs/adapter-evidence.md` | Candidate compatibility; standard trust | CLI provenance is necessary to know what candidate was exercised. For standard trust, it becomes part of the pinned adapter configuration identity. |
| `validate_run_dir.sh` requires a completed run record, non-empty patch, matching patch hash, and an existing base commit. | `scripts/validate_run_dir.sh`; `scripts/run_record.py` | Captured-run workflow; candidate compatibility; standard trust | This is core captured-run validation. A candidate compatibility result should pass it, and qualification requires it for each trust case. |
| `verify_patch.sh` validates the run, applies the patch from the recorded base in a detached verifier worktree, and runs target verification. | `scripts/verify_patch.sh`; `scripts/verifier_worktree.py` | Captured-run workflow; candidate compatibility; standard trust | This proves one captured patch is verifiable. It can support candidate compatibility, but by itself it does not prove standard trust. |
| Qualification cases add operator-controlled task text, allowed paths, and acceptance scripts. | `qualification/cases/*`; `scripts/qualification_case.py`; `scripts/qualify_adapter.sh` | Standard trust | This is trust evidence. It is stronger than needed for a lightweight candidate compatibility check unless the operator is intentionally starting qualification. |
| `qualify_adapter.sh` runs one captured run, validates it, verifies its patch, validates adapter identity, enforces allowed paths, applies the patch in a fresh acceptance worktree, runs task-specific acceptance, and writes a qualification result. | `scripts/qualify_adapter.sh`; `scripts/write_qualification_result.py`; `scripts/qualification_result.py` | Standard trust | This is the current standard-trust evaluation command. It should not be reinterpreted as a lightweight compatibility command without an explicit policy change. |
| The qualification series requires three consecutive passed cases: `behavior-change`, `new-behavior`, and `edge-case`, with a consistent pinned adapter configuration. Failures, unknown cases, duplicate cases, incomplete results, missing identity, and configuration drift reset the active series. | `scripts/qualification_result.py`; `tests/qualification_series/run_all.sh`; `docs/adr/0001-contiguous-adapter-qualification.md` | Standard trust | This is only necessary for standard trust. It is intentionally stronger than candidate compatibility. |
| The evidence register records qualified configurations, run IDs, task specs, acceptance specs, scope results, patch hashes, and drift rules. | `docs/adapter-evidence.md`; `scripts/qualification_report.py` | Standard trust | This is the committed audit record for trust decisions. It is not required to prove that a candidate CLI can perform a single compatible run. |
| Adapter registry status and trust fields distinguish `stable` / `experimental` / `blocked` and `standard` / `experimental` / `test-only`. | `docs/adapters.md` | Standard trust | Registry updates are trust/status decisions. A compatibility probe may inform them later, but does not update them by itself. |
| `check_adapters.sh` requires CLIs for standard adapters during the full health proof. | `scripts/check_adapters.sh`; `README.md`; `docs/adapters.md` | Standard trust; captured-run environment precondition | This proves host CLI availability for already-standard adapters. It does not substitute for compatibility evidence or qualification evidence. |
| Promotion validates the run, rejects stale bases, verifies before promotion, requires exact operator approval, creates `gate/<run-id>`, commits there, reruns verification, and writes `promotion.json`. | `scripts/promote.sh`; `README.md` | Captured-run / verified-patch workflow | Promotion is separate from adapter evaluation. Neither compatibility nor standard trust approves promotion. |

## Compatibility Checks Needed For A Candidate CLI

A lightweight candidate compatibility check should be limited to evidence that
the CLI can function inside the existing Axiom Forge loop:

1. The candidate command can be resolved and invoked from the shell context used
   by the adapter.
2. A minimal adapter can call the CLI with only the task file and supplied
   worktree as its operational boundary.
3. The CLI can complete a bounded task without committing, creating or deleting
   branches, changing `HEAD`, modifying the target checkout, or requiring access
   to the main repository.
4. The run produces a non-empty patch captured by `scripts/run_agent_task.sh`.
5. `record.json` includes CLI provenance for real CLI adapters.
6. `scripts/validate_run_dir.sh` accepts the captured run.
7. `scripts/verify_patch.sh` accepts the patch from a disposable verifier
   worktree.

Those checks are enough to show basic Axiom Forge compatibility for one
candidate configuration. They are not enough to grant `standard` trust because
they do not establish independent task coverage, contiguous reliability,
operator-controlled task-specific acceptance, scope conformance across the
qualification fixture, or configuration-drift handling.

## Checks Reserved For Standard Trust

The following current checks belong to the standard-trust decision:

- three contiguous independent qualification cases;
- the exact case set: `behavior-change`, `new-behavior`, and `edge-case`;
- reset-on-failure series evaluation;
- duplicate-case, unknown-case, incomplete-result, missing-identity, and
  configuration-drift resets;
- committed qualification result files;
- operator-controlled allowed-path enforcement for each qualification case;
- task-specific acceptance scripts applied after patch verification;
- consistent pinned adapter identity across adapter script revision, CLI
  command/path/version, selected model, and relevant configuration;
- committed evidence-register updates; and
- registry promotion to `stable` status and `standard` trust.

Existing qualification evidence remains interpretable under this split because
it already records the stronger trust inputs: qualifying run IDs, task
specifications, allowed-path specifications, acceptance specifications, patch
hashes, scope and acceptance outcomes, and pinned adapter configuration.
Compatibility results are separate local evidence and are not inputs to
qualification series evaluation.

## ADR Conflict To Surface

`docs/adr/0001-contiguous-adapter-qualification.md` says new adapters and
future changes follow the contiguous qualification rule before receiving
`standard` status and trust. A lightweight compatibility category is compatible
with that ADR only if it remains a pre-registration, non-trust, non-promotion
decision.

There would be a policy conflict if a future change used compatibility evidence
to register an adapter as `standard`, mark a configuration trusted, bypass the
three-case qualification series, or avoid the reset rules. That would require a
new ADR or an explicit amendment to ADR 0001 before command behavior or trust
policy changed.

## Practical Split For Future Work

- Keep `scripts/run_agent_task.sh`, `scripts/validate_run_dir.sh`, and
  `scripts/verify_patch.sh` as the core proof path for one captured run.
- Treat candidate compatibility as a bounded use of that proof path plus CLI
  provenance and adapter-safety observations.
- Keep `scripts/qualify_adapter.sh`, qualification cases, series evaluation,
  evidence-register updates, and registry trust changes reserved for standard
  adapter trust.
- Keep `scripts/promote.sh` independent: it promotes a verified captured patch
  only after exact operator approval, regardless of how the adapter is
  classified.
