# Self-Development Proposal Recovery

Genesis self-development must not fail merely because an otherwise available reasoning provider emits malformed structured output once.

The coding module therefore uses a bounded proposal-recovery protocol:

1. Request a JSON coding proposal with `title`, `rationale`, and a non-empty `files` mapping.
2. Extract the first balanced JSON object when providers wrap output in prose or code fences.
3. Validate all normal Coding safety boundaries and writable paths.
4. If parsing or schema validation fails, send the exact defect and the previous bounded output back to the same provider and request a corrected JSON-only proposal.
5. Retry at most three provider calls in total.
6. Never relax protected paths, byte limits, file-count limits, tests, security review, or independent validation to obtain a candidate.
7. If all bounded attempts fail, keep the issue unresolved/blocked so another pulse can retry with new evidence or a different provider.

Recovery improves formatting reliability only. It does not make model output trusted or canonical.
