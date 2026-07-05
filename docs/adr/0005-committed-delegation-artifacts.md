# Committed Delegation and Review Evidence

Delegation artifacts must be committed to the Forge repository before an adapter run begins, and promotion review results must be committed before promotion. This trades some local iteration convenience for auditability: each captured run can point back to an exact approved revision of the runnable task file, approved path-scope sidecar, and operator-approved acceptance check that the adapter received, while each promotion can point back to a stable review result. The captured run record should identify the Forge commit SHA for its delegation artifacts, and the promotion record should identify the Forge commit SHA for the review result it relied on, so both delegation authority and promotion authority are reconstructable later.

