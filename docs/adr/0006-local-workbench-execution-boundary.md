# Bound local workbench execution to task-to-captured-run

The first operator workbench will be a local browser UI that may execute only the explicitly confirmed task-to-captured-run workflow: target-mode adapter run followed by target-mode verification. Promotion remains outside the first UI and continues through the existing fail-closed gate, so the workbench reduces delegation friction without becoming a generic command runner, autonomous orchestrator, or promotion surface.
