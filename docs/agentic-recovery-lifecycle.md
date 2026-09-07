# Agentic recovery lifecycle

Genesis does not treat a failed repair method as completion or as permission to close the Issue.

1. Normal bounded repair is the first method.
2. If that lane cannot verify a repair, the same authoritative Issue is handed to Agentic Lab.
3. Agentic Lab records each failed method and rotates through materially different strategies:
   - `evidence_first`
   - `alternative_implementation`
   - `diagnostic_reframe`
   - `dependency_diagnosis`
4. A failed Agentic strategy leaves the Issue open and returns control to Agentic Lab for the next method.
5. If the remaining blocker is a missing Genesis repair capability, Agentic Lab creates or reuses one linked capability Issue, marks the parent `genesis-waiting-capability`, and pauses target retries while keeping the parent open.
6. When the capability Issue is verified/completed, the parent is released for a fresh strategy cycle.
7. Capability-building work does not create an unbounded dependency chain. If materially different safe strategies still fail on the capability Issue, it remains open with `genesis-needs-human` for maintainer review.
8. Only a verified and promoted target repair closes a normal Issue as completed.

All existing tests, Security, protected-file boundaries, signing, secret boundaries, independent validation, exact promotion, and owner controls remain mandatory throughout the lifecycle.
