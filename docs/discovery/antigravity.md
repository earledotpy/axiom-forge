# Antigravity Discovery

Date: 2026-06-16

## Local CLI

Antigravity exposes a Git Bash-callable CLI as:

```text
agy
````

Detected path:

```text
/c/Users/jerem/AppData/Local/agy/bin/agy
```

Detected version:

```text
1.0.8
```

Basic non-interactive prompt test:

```bash
agy -p "Say READY and do not edit files."
```

Observed output:

```text
READY
```

## Adapter Fit

Antigravity is potentially adapter-compatible because:

* `agy` is callable from Git Bash,
* `agy -p` accepts a prompt,
* `agy -p` can return output without opening an interactive session.

Not yet proven:

* whether `agy` reliably edits files in a supplied worktree,
* whether `agy` respects a worktree-only instruction,
* whether it exits cleanly after file-editing tasks,
* whether it creates commits or branches,
* whether it touches state outside the worktree.

## Decision

Antigravity is eligible for a cautious adapter experiment.

It is not yet trusted as a standard adapter until it passes the runner contract:

```text
agents/antigravity.sh <task_file> <worktree>
```

The adapter must:

* edit only the provided worktree,
* not commit,
* not create branches,
* not change HEAD,
* leave a diff,
* exit nonzero on failure.

