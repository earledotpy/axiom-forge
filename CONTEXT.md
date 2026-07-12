# Axiom Forge

Axiom Forge is a fail-closed patch verification and promotion gate for code produced by CLI coding agents.

## Language

**Candidate adapter**:
A product-specific CLI target under evidence-led investigation before it is implemented or registered as an Axiom Forge adapter.
_Avoid_: supported adapter, approved adapter

**Feasibility probe**:
A bounded disposable experiment that establishes whether a candidate adapter can express a required invocation constraint. It is neither a captured run nor adapter qualification evidence.
_Avoid_: qualification run, acceptance test

**Captured run**:
The evidence directory produced from one agent invocation, including its run record and patch. A captured run may be verified without being promoted.
_Avoid_: execution, job

**Superseded captured run**:
A captured run preserved as evidence after the operator reruns its task from a newer approved target base or replacement delegation artifact set. It is visible in task history but is not a promotable input.
_Avoid_: deleted run, hidden failure, current run

**Target-mode captured run**:
A captured run produced with explicit target mode, where the patch applies to the configured external target repository while the run evidence remains Forge-owned.
_Avoid_: target execution, external job

**Captured run record**:
The structured evidence item inside a captured run that identifies the run, agent, base, task, patch, CLI provenance, and completed or failed status.
_Avoid_: log, qualification report, promotion record

**Verified patch**:
A captured run's patch that passes run-directory validation and patch verification from its recorded base in a fresh detached worktree. Verification does not approve or promote the patch.
_Avoid_: approved patch, promoted patch

**Promotion-ready patch**:
A verified patch with a passing promotion review result, a non-stale delegation target base, and satisfied approved scope and acceptance evidence. Promotion-ready does not itself promote the patch; explicit operator approval is still required.
_Avoid_: verified patch, automatically approved patch, promoted patch

**External target repository**:
A repository outside the Axiom Forge checkout that Axiom Forge is asked to modify through captured runs, verified patches, and explicit promotion.
_Avoid_: embedded Forge repo, managed subproject

**Primary target repository**:
The single external target repository selected for Axiom Forge's first real integration milestone.
_Avoid_: arbitrary target repo, multi-repo target set

**Target repository configuration**:
Forge-owned configuration that identifies the primary target repository and its expected base branch for target-repo runs.
_Avoid_: repeated target path argument, implicit working directory target

**Forge-owned evidence**:
Captured run, verification, and promotion records stored by Axiom Forge for an external target repository run rather than committed into the target repository source tree.
_Avoid_: target-owned run evidence, application source evidence files

**Operator workbench**:
The user-facing workflow surface where an operator turns planning source material into bounded patch tasks, delegates approved tasks to CLI adapters, inspects captured evidence, and chooses retry, review, or promotion.
_Avoid_: orchestrator, dashboard-only UI, autonomous agent manager

**Local workbench UI**:
The first operator workbench surface: a browser-based local UI backed by Forge-owned files and the existing runner, verifier, and evidence commands. It may execute only the confirmed task-to-captured-run workflow and does not replace the fail-closed promotion gate.
_Avoid_: terminal-only workflow, TUI, remote dashboard, generic command runner

**Workbench state source**:
The first local workbench derives state from GitHub Issues, committed Forge delegation artifacts, captured run evidence, and verification outputs rather than a separate persistent database. A later workbench version may add a database after the task-to-captured-run workflow proves what state must be stored.
_Avoid_: Forge project database, permanent no-database rule, duplicated planning store

**Task-to-captured-run workflow**:
The first operator workbench workflow: turn planning source material into approved delegation artifacts, run a selected adapter in target mode after explicit operator confirmation, verify the captured run, and inspect the resulting evidence. It stops before promotion; promotion remains a separate gate decision.
_Avoid_: promotion workflow, adapter qualification, autonomous implementation loop

**Active workbench delegation**:
The single task-to-captured-run workflow that the first local workbench may execute at one time. The workbench may show historical captured runs, but it does not start or manage concurrent adapter delegations in its first version.
_Avoid_: concurrent delegation, background task queue, multi-agent scheduler

**Operator evidence summary**:
The first post-run workbench view of structured evidence for a task: task intent, approved scope, adapter, run status, changed paths, verification result, acceptance result, failure reason, and next allowed actions. Raw logs and patch diffs are supporting drill-down material, not the primary operator view.
_Avoid_: terminal transcript, raw log view, patch-first view

**Promotion review**:
A planner or operator review of a verified patch before promotion. It is required even when the patch passes its deterministic acceptance check, because acceptance proves only the bounded task behavior.
_Avoid_: automatic approval, acceptance-only promotion, adapter self-review

**Promotion review result**:
The committed structured evidence produced by promotion-review mode for a verified patch, recording reviewer identity, reviewed run or patch, decision, concerns or no-concerns statement, and any follow-up bounded patch tasks. A conversational approval alone is not a promotion review result.
_Avoid_: looks-good comment, chat approval, informal review note

**Promotion review revision**:
The Forge commit SHA identifying the exact committed promotion review result used for a promotion. It lets promotion evidence point back to the reviewed patch decision it relied on.
_Avoid_: latest review, chat approval, implicit review evidence

**Review-requested refactor**:
A refactoring change identified during promotion review. It becomes a separate bounded patch task unless it is a tiny fix within the same operator-approved scope.
_Avoid_: unbounded review fix, hidden second implementation, scope expansion

**Target promotion**:
Promotion of a verified patch onto a gate branch in the external target repository while Axiom Forge retains the promotion evidence.
_Avoid_: Forge-repo promotion, direct main update

**Target-owned verification**:
The external target repository's configured checks run by Axiom Forge in a disposable verifier worktree to verify a captured patch for that target.
_Avoid_: Forge health check, adapter qualification acceptance

**Delegation target base**:
The operator-approved target repository base SHA that a delegation-ready task is intended to modify. The UI may propose it from the configured target branch and warn if it becomes stale before delegation; promotion treats a stale target base as a fail-closed blocker resolved by rerunning from a newly approved base, not by silently rebasing the captured patch. It is distinct from the delegation artifact revision, which identifies the Forge commit containing the approved task, scope, and acceptance check.
_Avoid_: Forge revision, latest target branch, implicit base

**Target task scope**:
The operator-controlled list of external target repository paths a target-mode captured run may modify. A target-mode patch outside this list fails closed before target promotion.
_Avoid_: implied target scope, broad target task

**Draft task scope**:
A planner-proposed list of paths for a bounded patch task before operator approval. It is not adapter authority until the operator accepts or revises it into the target task scope.
_Avoid_: approved scope, implicit scope, adapter-selected scope

**Planning source of truth**:
The GitHub Issues and project docs that hold high-level plans, PRDs, and decomposed task intent. The first operator workbench reads GitHub Issues before drafting delegation artifacts; Forge owns only the delegation artifacts and evidence needed for patch gating.
_Avoid_: Forge project database, UI-only plan, duplicated PRD store

**Planner role**:
The authority that turns a high-level plan into bounded patch tasks for adapters. It may draft task files and task scopes, but implementation adapters do not hold this role.
_Avoid_: implementation adapter, autonomous agent, router

**Assisted task drafting**:
The operator workbench activity that helps turn planning source material into a draft task artifact while leaving scope, acceptance, adapter selection, and delegation approval under operator control.
_Avoid_: automatic task generation, silent delegation, autonomous planning

**Planner conversation**:
The UI-supported conversational workflow for a planner role, separated into task-drafting mode and promotion-review mode. It is distinct from delegated adapter interaction, which is non-chat implementation through approved tasks and captured results.
_Avoid_: adapter chat, implementation steering, raw CLI session

**Operator-approved acceptance check**:
A deterministic acceptance check drafted for a bounded patch task and accepted by the operator as proving the requested behavior. It lives outside the adapter's allowed path scope and is required before implementation delegation.
_Avoid_: planner-only check, adapter-selected check, manual review

**Operator-directed retry**:
A deliberate planner or operator choice to rerun a delegation-ready task after a failed captured run, optionally with a different adapter. The workbench may present retry choices and availability hints, but Forge records the failure as evidence and does not automatically reroute the task.
_Avoid_: automatic fallback, quota router, silent retry, autonomous failover

**Adapter availability failure**:
A failed captured run whose failure reason indicates the selected adapter was unavailable or out of quota before implementation correctness could be judged. It remains run evidence, but it is distinct from unsafe behavior or task-incorrect implementation.
_Avoid_: unsafe adapter failure, incorrect implementation, quota hint

**Adapter availability hint**:
Operator-visible information about whether an adapter may currently be usable, such as recent quota or availability signals. It is advisory only and is not trusted evidence for verification, promotion, or automatic routing.
_Avoid_: trusted quota state, routing decision, capacity guarantee

**Draft adapter selection**:
A planner or operator preference for which adapter might receive a bounded patch task. It is planning metadata only and does not delegate work until the task is delegation-ready.
_Avoid_: delegated run, adapter assignment, automatic routing

**Delegated adapter interaction**:
The permitted UI interaction model for implementation adapters: the operator delegates an approved task and inspects captured results. The UI may show run status and logs, but it does not provide live chat or mid-run steering for the adapter.
_Avoid_: live adapter chat, interactive steering, informal instruction update

**Concurrent task scope conflict**:
An overlap between the operator-approved scopes of active delegation-ready tasks. It must be resolved before parallel delegation so each captured run remains attributable to one bounded task.
_Avoid_: shared task scope, parallel file overlap, implicit merge conflict

**Draft task artifact**:
An operator-editable task draft produced from planning source material before it becomes a runnable task file. It may include proposed behavior, draft task scope, acceptance check, and draft adapter selection, but it is not adapter-facing authority.
_Avoid_: runnable task file, delegated task, hidden plan state

**Delegation artifact set**:
The committed runnable task file, approved path-scope sidecar, and operator-approved acceptance check created together from an approved draft task artifact. The set must stay synchronized because it is the adapter-facing delegation authority; changes return it to draft state and require regeneration. `scripts/delegation_artifact_set.py` is the internal ownership point for Delegation artifact set readiness, committed artifact lookup, and copied Forge-owned evidence rules; shell commands remain the operator-facing interfaces.
_Avoid_: partial task files, separate approval outputs, unsynchronized delegation files

**Delegation artifact revision**:
The Forge commit SHA identifying the exact committed delegation artifact set used for a captured run. It lets run evidence point back to the approved task, scope, and acceptance check the adapter received.
_Avoid_: local draft version, latest task file, implicit approval revision

**Delegation-ready task**:
A bounded patch task with operator-approved scope and a deterministic acceptance check. Implementation adapters may receive only delegation-ready tasks.
_Avoid_: unchecked task, review-only task, informal task

**Bounded patch task**:
A planner-authored task sized as the largest meaningful patch that still has clear scope and deterministic acceptance. It specifies desired behavior and constraints without prescribing implementation unless necessary, and delegates implementation only, not planning authority, review authority, or promotion authority.
_Avoid_: high-level goal, autonomous workflow, free-form agent job

**Registered adapter**:
An adapter listed in the Axiom Forge adapter inventory. Registration is distinct from one successful captured run and does not itself imply standard status or trust.
_Avoid_: approved adapter, trusted agent

**Candidate adapter compatibility result**:
Structured evidence that one candidate adapter configuration completed Axiom Forge's captured-run and verified-patch path. It answers basic CLI operability only; it is not adapter qualification evidence, standard trust, registration, or promotion approval.
_Avoid_: qualification result, trust result, approval

**Standard adapter**:
A registered adapter granted `standard` status and trust after documented adapter qualification. Promotion is not required for this qualification decision.
_Avoid_: promoted adapter, experimental adapter

**Adapter qualification**:
Supporting evidence for deciding whether a registered adapter configuration may receive standard trust. It is not the main operator workbench workflow; day-to-day implementation work uses delegation, captured runs, review, retry, and promotion decisions.
_Avoid_: main product loop, smoke test, one-off success

**Task-specific acceptance test**:
A deterministic, operator-controlled check that establishes whether one qualification task's requested behavior was implemented. It is kept outside the agent worktree and run after applying the captured patch in a fresh verifier worktree; it is distinct from the general project verification command.
_Avoid_: smoke test, manual review

**Qualification task scope**:
The operator-controlled list of paths a qualification patch may modify. A change outside this list makes the qualification attempt fail.
_Avoid_: implied scope, broad task

**Independent qualification tasks**:
The three distinct task categories used for one adapter qualification: `behavior-change` (modifying existing behavior), `new-behavior` (adding a small new behavior), and `edge-case` (handling a defined edge case). Variations of one edit type do not form a qualifying series.
_Avoid_: repeated task, string-only variations

**Qualification fixture**:
The dedicated source fixture and acceptance harness used for adapter qualification. It is separate from Axiom Forge's general sample application and test suite.
_Avoid_: general test fixture, production task

**Qualification command**:
The dedicated command that evaluates one adapter against one qualification case. It captures the run, verifies the patch, enforces task scope, runs external acceptance, captures configuration identity, and writes a qualification result.
_Avoid_: manual run sequence, ad hoc checklist

**Qualification result**:
The structured evidence record produced by one qualification command evaluation. The qualification command writes it and the operator commits it. Once committed, it is a permanent element of that adapter's qualification history and cannot be excluded from series evaluation.
_Avoid_: qualification log, run verdict

**Qualification series**:
The complete ordered sequence of committed qualification results for one adapter, derived automatically in run-ID order without operator selection. The series is qualifying when it ends with an unbroken streak of PASSED results covering all three required case types with a consistent pinned adapter configuration.
_Avoid_: result batch, selected evidence set

**Qualification case**:
A committed directory containing one agent-visible task and its operator-controlled allowed paths and acceptance code. The qualification command supplies only the task to the agent.
_Avoid_: inline task, mutable test

**Qualification report**:
The committed audit record supporting an adapter registration decision. It identifies the qualifying runs, pinned adapter configuration, task specifications, acceptance and scope results, and patch hashes without treating ignored raw run artifacts as source files.
_Avoid_: raw run directory, verbal approval

**Adapter configuration**:
The reproducible identity of one adapter qualification target: the adapter-script revision, CLI version, selected model, and relevant configuration. Registration applies to this configuration rather than to a CLI product name alone.
_Avoid_: adapter name, provider

**Qualification configuration declaration**:
The operator-committed file stating the selected model and relevant configuration for one adapter's qualification. Combined with the adapter-script revision and the CLI provenance captured at run time, it completes the adapter configuration identity recorded in each qualification result.
_Avoid_: adapter config file, settings file

**Configuration drift**:
A change to a standard adapter's adapter-script revision, CLI version, selected model, or relevant configuration. Drift invalidates standard trust until the changed configuration completes a new adapter qualification.
_Avoid_: harmless upgrade, unchanged adapter
