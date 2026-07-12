# Limit the first workbench to one active delegation

The first local operator workbench will execute at most one active task-to-captured-run workflow at a time while showing historical captured runs as read-only evidence. This postpones concurrent adapter delegation until a single real target workflow is proven, avoiding early scope-overlap, stale-base, adapter-availability, and evidence-state complexity while preserving the option to add concurrency later.
