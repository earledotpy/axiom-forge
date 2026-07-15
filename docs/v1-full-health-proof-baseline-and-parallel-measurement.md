# Full-Health Proof Baseline and Clone-Isolated Measurement

## Decision

A clone-isolated parallel proof runner is a viable next implementation experiment.
In one complete same-SHA trial, it ran every current required stage unchanged and
reduced wall-clock time by 52.9%. Do not change `scripts/forge_check.sh` yet:
repeat this measurement at least three times from clean, synchronized `main`
and add a tested aggregate runner before adopting it.

## Method

On 2026-07-14, the original full proof and the candidate both used Forge commit
`7bf420c1f2eac83289c51d6504a62d75c80a4347`. The source workspace was
preserved; every run used disposable local clones. `PYTHONDONTWRITEBYTECODE=1`
prevented bytecode artifacts from affecting clean-tree checks, and harness logs
were outside each tested clone.

The baseline invoked the unchanged
[`scripts/forge_check.sh`](../scripts/forge_check.sh). The candidate created
eleven fresh clean clones at the same SHA, checked each clone's SHA and clean
status before dispatch, then invoked each existing command unchanged in one
clone. Its coordinator waited for all eleven exit results and emitted the
existing `AXIOM_FORGE_CHECK: PASS` sentinel only after every result was zero.

## Completed sequential baseline

The original script reached its sole success sentinel in **897.466 s** (14m
57.5s), measured from `AXIOM_FORGE_CHECK: START` to
`AXIOM_FORGE_CHECK: PASS`.

| Required stage | Elapsed |
| --- | ---: |
| Adapter CLI preflight | 16.512 s |
| Gate-contract matrix | 1.839 s |
| Promotion matrix | 312.470 s |
| Runner matrix | 91.993 s |
| Target-verification matrix | 80.867 s |
| Target-operator-loop matrix | 20.773 s |
| Operator-workbench tests | 17.769 s |
| Compatibility matrix | 45.266 s |
| Adapter-evaluation matrix | 55.412 s |
| Qualification matrix | 251.067 s |
| Qualification-series matrix | 3.403 s |

## Completed clone-isolated candidate

All eleven logs recorded the same SHA and exit code zero. The aggregate
coordinator then printed `AXIOM_FORGE_CHECK: PASS`.

- Clone setup: **9.313 s**
- Aggregate execution: **413.466 s** (6m 53.5s)
- Setup plus execution: **422.779 s** (7m 2.8s)
- Reduction against the sequential baseline: **474.687 s** / **52.9%**
- Observed speedup: **2.12x**

The two longest concurrent legs were qualification (412.970 s) and promotion
(391.040 s). Their isolated durations were longer than their sequential
durations because they contended for the same host, but overlapping them still
reduced end-to-end wall time.

## Guardrails

The candidate did not run matrices concurrently in one checkout. That would
race on mutable Forge state: the promotion, runner, target-verification, and
target-operator-loop matrices write fixtures such as `gate.toml`, `runs/`,
branches, worktrees, or target repositories. The required commands and their
current ordering are owned by
[`scripts/forge_check.sh`](../scripts/forge_check.sh); it fails fast and has
no success authority other than its final sentinel.

A future implementation must therefore:

1. resolve one clean, synchronized `main` SHA before dispatch;
2. run the adapter preflight and every current matrix unchanged in isolated
   clean clones at that SHA;
3. retain per-stage start, outcome, elapsed time, SHA, and stdout/stderr;
4. treat setup failure, timeout, cancellation, missing results, SHA mismatch,
   or nonzero exit as incomplete or failed evidence; and
5. print `AXIOM_FORGE_CHECK: PASS` only after all required results pass.

This one completed local trial establishes feasibility and a performance signal;
it is not release proof and does not authorize caching, selected-matrix proof,
advisory preflight, or any change to the current health gate.
