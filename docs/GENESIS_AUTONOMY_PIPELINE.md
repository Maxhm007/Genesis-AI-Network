# Genesis Autonomy Pipeline

Genesis autonomous software development is organized as specialist workers over one persistent work queue. The authoritative task database remains `runtime/genesis_tasks.sqlite3`; pipeline metadata is stored beside the task records in the same SQLite database and keyed by the same task ID.

## Pipeline

```text
Discovery
   ↓
Triage
   ↓
Repair
   ↓
Internal Review
   ├── needs repair ─────────────┐
   │                             │
   └── approved                  │
          ↓                      │
Independent Validation           │
          ↓                      │
Promotion                        │
          ↓                      │
Learning                         │
          ↓                      │
Closed                           │
                                 │
Repair  ◄────────────────────────┘
```

### Discovery worker

Ranks Genesis source by evidence and risk, then asks a non-bootstrap reasoning provider to confirm one concrete testable issue. It may create queue work, but it cannot edit code.

### Triage worker

Rejects protected targets, missing targets, weak-confidence findings, and invalid queue state. Accepted tasks move to `repair_ready`.

### Repair worker

Uses the existing bounded `AutonomousEngineeringLoop` / Coding / DevLab candidate path. A successful repair must pass the existing candidate Security review. The exact candidate is placed on an isolated `genesis/review-*` ref; this ref does not open the normal autonomous candidate PR.

### Review worker

Checks out the exact isolated review SHA, runs the full test suite again, and performs an independent internal reasoning review against the original task objective and diff. Its decision is either:

- `approve` → `validation_ready`
- `needs_repair` → same task ID returns to the Repair worker with review feedback

A repair is never published as `genesis/candidate-*` before this review passes.

### Validation worker

Does not validate its own work and does not promote code. It waits for the existing GitHub validation/promotion system. Publishing the exact internally-approved SHA to `genesis/candidate-*` activates the existing candidate PR opener, independent validators, Security review, signed quorum, and promotion controls.

### Promotion observer

Observes whether the exact candidate or an equivalent safely-rebased patch reached `main`. It has no direct-main write authority.

### Learning worker

Records the complete issue/repair/review/promotion history as durable learning evidence, marks the queue task complete, and allows Genesis to discover the next issue.

## Queue stages

```text
discovered
  → repair_ready
  → review_ready
      → needs_repair → repair_ready
      → validation_ready
          → promoted
              → closed

invalid / exhausted work → quarantined
```

## Safety boundaries

The pipeline does not change Genesis's promotion trust model:

- no direct write to `main`;
- no autonomous edit of protected identity/security/control-plane files;
- no validation authority for Discovery, Triage, Repair, Review, or Learning;
- candidate Security review remains mandatory;
- independent validators and signed quorum remain mandatory;
- exact reviewed candidate identity is preserved through handoffs;
- failed internal review returns evidence to Repair instead of weakening tests or validation.

## Pulse behavior

Gene Pulse is now a coordinator/wakeup mechanism. One Pulse performs at most one bounded specialist transition, persists state, and chains only when another executable stage exists. Validation waits and no-issue discovery checkpoint instead of spinning.
