# Defer a persistent workbench database

The first local operator workbench will derive state from GitHub Issues, committed Forge delegation artifacts, captured run evidence, and verification outputs instead of introducing a persistent database. This keeps the first version focused on proving the task-to-captured-run workflow without creating a second planning source of truth, while leaving room for a later database once real use shows which state must outlive a local session.
