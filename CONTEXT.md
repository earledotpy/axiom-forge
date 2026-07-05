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

**Target-mode captured run**:
A captured run produced with explicit target mode, where the patch applies to the configured external target repository while the run evidence remains Forge-owned.
_Avoid_: target execution, external job

**Captured run record**:
The structured evidence item inside a captured run that identifies the run, agent, base, task, patch, CLI provenance, and completed or failed status.
_Avoid_: log, qualification report, promotion record

**Verified patch**:
A captured run's patch that passes run-directory validation and patch verification from its recorded base in a fresh detached worktree. Verification does not approve or promote the patch.
_Avoid_: approved patch, promoted patch

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

**Target promotion**:
Promotion of a verified patch onto a gate branch in the external target repository while Axiom Forge retains the promotion evidence.
_Avoid_: Forge-repo promotion, direct main update

**Target-owned verification**:
The external target repository's configured checks run by Axiom Forge in a disposable verifier worktree to verify a captured patch for that target.
_Avoid_: Forge health check, adapter qualification acceptance

**Target task scope**:
The operator-controlled list of external target repository paths a target-mode captured run may modify. A target-mode patch outside this list fails closed before target promotion.
_Avoid_: implied target scope, broad target task

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
The required evidence for registering an adapter: three consecutive, independent, successful, in-scope captured runs, each satisfying the full adapter-safety contract, producing a verified patch, capturing a complete adapter configuration, and passing a deterministic task-specific acceptance test. A failed, unsafe, incompletely identified, or task-incorrect run resets the qualification series; manual assertions do not substitute for captured identity evidence.
_Avoid_: smoke test, one-off success

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
