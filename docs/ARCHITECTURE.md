# Architecture Overview

This diagram shows the core components and flows in Axiom Forge: operator workbench, runner, adapters (CLI agents), verification, and promotion.

```mermaid
flowchart LR
  subgraph Operator
    OP[Operator / Workbench]
  end

  subgraph ForgeRepo[Forge Repository]
    ROOT[Repository (main)]
    SCRIPTS[scripts/*]
    AGENTS[agents/* (adapter scripts)]
    RUNS[runs/ (captured run dirs - gitignored)]
    REVIEWS[reviews/promotion/*]
    CONFIG[gate.toml]
  end

  OP -->|creates task & approves| ROOT
  OP -->|starts run (run_agent_task.sh)| SCRIPTS

  SCRIPTS -->|creates disposable worktree| WT[Disposable worktree]
  WT -->|invokes adapter CLI| ADP[Adapter script (agents/<name>.sh)]
  ADP -->|edits files inside worktree only| WT
  SCRIPTS -->|captures patch & record| RUNS

  RUNS -->|validate_run_dir.sh| SCRIPTS
  RUNS -->|verify_patch.sh (verifier_worktree.py)| SCRIPTS
  SCRIPTS -->|on success and operator approval| SCRIPTS_PROM[ promote.sh ]

  SCRIPTS_PROM -->|create gate/<run-id> branch from base SHA| GATEBR[gate/<run-id> branch]
  GATEBR -->|apply patch & commit| PROM_COMMIT[Promotion commit]
  PROM_COMMIT -->|post-promotion verification| SCRIPTS
  PROM_COMMIT -->|write promotion.json| RUNS

  subgraph ExternalTarget[Optional: External Target Repository]
    TARGET[Target repository (target mode)]
  end

  CONFIG -.-> TARGET
  SCRIPTS -.->|target_preflight.py & target_verify.py| TARGET
  RUNS -->|allowed-paths.txt (target scope)| SCRIPTS
  SCRIPTS_PROM -.->|create gate/<run-id> in target repo| TARGET

  %% Annotations
  classDef config fill:#f9f,stroke:#333,stroke-width:1px;
  class CONFIG config;

  note right of WT: created by runner
  note right of RUNS: evidence: record.json, patch.diff, logs, promotion.json
  note left of ADP: must not modify Forge main or create branches
  note right of GATEBR: created only by promote.sh after approval
```

Notes

- The Runner (scripts/run_agent_task.sh) is the single control loop that creates disposable worktrees, runs adapters, captures patches and writes runs/<run-id> evidence.
- Verification is deterministic: verify_patch.sh creates a detached verifier worktree from the recorded base SHA and runs configured checks (verifier_worktree.py).
- Promotion is fail-closed: promote.sh enforces run validation, verification, promotion review evidence, operator-typed run-id approval, and creates gate/<run-id> branches.
- gate.toml configures primary target repository and verification commands (target mode).

References: README.md, CONTEXT.md, scripts/run_agent_task.sh, scripts/verify_patch.sh, scripts/promote.sh, gate.toml
