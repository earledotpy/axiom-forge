# Deepen captured run record ownership

Captured run record rules belong in an internal Python library module at `scripts/run_record.py`, while the existing shell scripts remain the operator-facing interfaces. New writes should use the current strict schema, validation should remain backward-compatible only where existing behavior already requires it, and historical run evidence should not be migrated as part of this refactor. This keeps Axiom Forge's Bash-based workflow stable while concentrating record schema, status, run ID, and patch-hash rules behind one deeper module.
