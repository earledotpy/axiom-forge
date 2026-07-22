# Bound local workbench execution to task-to-captured-run

The first operator workbench will be a local browser UI that may execute only the explicitly confirmed task-to-captured-run workflow: target-mode adapter run followed by target-mode verification. Promotion is now surfaced only through the later Stage 3 UI described by ADR 0013, which invokes the existing fail-closed gate without replacing it; so the workbench reduces delegation friction without becoming a generic command runner, autonomous orchestrator, or promotion surface.
