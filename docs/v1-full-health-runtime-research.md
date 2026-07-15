# V1 Full-Health Proof Runtime Research

## Decision

Retain one authoritative, fail-closed `scripts/forge_check.sh` result. The
first runtime-reduction experiment should be a **clone-isolated parallel proof
runner**: it launches independent existing stages in separate clean clones,
collects every stage result, and emits `AXIOM_FORGE_CHECK: PASS` only after all
required stages pass. Do not parallelize the existing matrices in the same
checkout, drop a matrix, replace a matrix with a smoke test, cache a prior
PASS, or make the required adapter preflight advisory.

This is an implementation recommendation, not an optimization applied by this
research note.

## Evidence

### Current full-proof contract

[`scripts/forge_check.sh`](../scripts/forge_check.sh) first rejects a dirty
tree, then runs the required adapter CLI preflight and ten validation stages
sequentially. Its final `AXIOM_FORGE_CHECK: PASS` line is the only success
authority. The contract agreed for v1 also requires per-stage lifecycle and
elapsed-time evidence, an overall timeout whose expiry is incomplete evidence,
and a release record tied to the tested `main` SHA rather than its later
evidence commit.[^contract]

The clean-tree condition and full-matrix coverage are intentional. The
non-recursive gate design says the health proof remains manual and must not be
reached from promotion-time verification.[^non-recursive]

### Measurement

On 2026-07-14, a disposable local clone of the current tracked snapshot
(`7bf420c`) was given a local `main` branch pointing at that snapshot and run
with `PYTHONDONTWRITEBYTECODE=1`. Harness logs were stored outside the clone
so the proof's clean-tree precondition remained true. This is a local timing
sample, not v1 release evidence: it is neither synchronized remote `main` nor
a complete `AXIOM_FORGE_CHECK: PASS` record.

| Stage | Exit | Elapsed | Interpretation |
| --- | --- | ---: | --- |
| `scripts/check_adapters.sh` | 0 | 19 s | Required live CLI/version preflight; a separate cold attempt took 53 s. |
| `tests/gate_contract/run_all.sh` | 0 | 2 s | Static non-recursion and required-CLI contract checks. |
| `tests/promote/run_all.sh` | running when sampled | over 40 s | First long-running mutable stage; it runs the Python unit suite and exercises both Forge and target promotion paths. |

The previous timing attempt is excluded: writing its harness log inside the
clone made the repository dirty and correctly caused later matrices to reject
the run. That result demonstrates that timing instrumentation must be external
to the tested checkout.

### Why same-checkout parallelism is unsafe

The long matrices each assume a clean root and change shared test state:

- [`tests/promote/run_all.sh`](../tests/promote/run_all.sh) writes `gate.toml`,
  creates `runs/` fixtures, creates/deletes `gate/<run-id>` branches, and
  creates target repositories.
- [`tests/runner/run_all.sh`](../tests/runner/run_all.sh),
  [`tests/target_verify/run_all.sh`](../tests/target_verify/run_all.sh), and
  [`tests/target_operator_loop/run_all.sh`](../tests/target_operator_loop/run_all.sh)
  also require a clean root and create fixture runs, worktrees, or temporary
  target repositories.
- [`tests/compatibility/run_all.sh`](../tests/compatibility/run_all.sh),
  [`tests/adapter_evaluation/run_all.sh`](../tests/adapter_evaluation/run_all.sh),
  and [`tests/qualification/run_all.sh`](../tests/qualification/run_all.sh)
  create internal clone sandboxes and run captured-run/verification flows.

Those shared names and repository-level mutations make direct backgrounding in
one checkout a race that can turn a valid result into misleading evidence.

## Recommended experiment

1. Preserve the existing preflight and resolve the tested clean synchronized
   `main` SHA once.
2. Create one disposable clean clone per mutable matrix. Run each existing
   command unchanged in its clone; the static gate-contract check and
   read-only Python tests may also receive their own clone for a uniform
   harness.
3. Give each child an explicit `START`, `PASS`/`FAIL`, elapsed time, tested
   SHA, and captured stdout/stderr path. On timeout, interruption, setup
   failure, or a nonzero child result, report the active stage as incomplete
   or failed exactly as the v1 evidence contract requires.
4. The parent waits for every required result. It prints the existing final
   PASS sentinel only if all children passed for the same SHA; otherwise it
   prints no PASS sentinel and preserves the child evidence.
5. Compare wall-clock time, per-stage time, and outcomes across at least three
   clean synchronized `main` trials against the sequential baseline. Accept it
   only if every existing matrix executes unchanged and no final-result or
   cleanup invariant regresses.

This can reduce wall-clock time toward the longest isolated stage rather than
the sum of all stages. The exact gain is deliberately unclaimed until the
complete baseline and three-trial comparison exist.

## Secondary candidates, after the isolation experiment

- **Remove verified duplicate unit execution at the top level.** The promotion
  matrix invokes `python -m unittest discover -s tests`, while the top-level
  script later invokes three of those workbench modules again. A coverage-manifest
  experiment could run each Python test module exactly once in the full proof
  while keeping the promotion matrix self-contained when run directly. This is
  safe only if the test-ID manifest proves no module was lost.
- **Bound each CLI version probe.** `check_adapters.sh` tries `--version`, then
  `-V`, then `version` without a per-command timeout. Add a short fail-closed
  timeout only after confirming every required adapter's supported version
  syntax. A timeout must produce the existing required-CLI failure, never a
  silent "available" result.

Do not pursue a cached PASS, an optional required adapter, a selected-matrix
release proof, or promotion-time health invocation; each would weaken the
current contract or violate the non-recursive boundary.

[^contract]: [Define the full-health proof observability and v1 evidence contract](https://github.com/earledotpy/axiom-forge/issues/61#issuecomment-4974178919), resolution read 2026-07-14.
[^non-recursive]: [`docs/v0.3-non-recursive-gate-contract-design.md`](v0.3-non-recursive-gate-contract-design.md), "Manual full-health invariants" and "Non-recursion proof".
