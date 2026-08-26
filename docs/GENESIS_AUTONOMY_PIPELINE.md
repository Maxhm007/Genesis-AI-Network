# Genesis Autonomy Pipeline

Genesis autonomous work is organized around **GitHub Issues as the single authoritative task source**. `runtime/genesis_tasks.sqlite3` remains only a resumable execution/cache database; a SQLite row cannot independently authorize work. Every autonomous task must create, reuse, or adopt a GitHub Issue before any worker may execute it.

The governing invariant is:

> **No GitHub Issue = no Genesis task execution.**

Normal actionable Issues created by the owner or another user enter the same autonomous intake automatically. Genesis-created discoveries, repairs, research tasks, benchmark work, capability additions, self-improvements, and maintenance tasks must publish an Issue before execution.

## Pipeline

```text
Discovery / Owner-created Issue
          ↓
GitHub Issue authority
          ↓
Local execution-state binding
          ↓
Triage
   ↓
Development / Repair
   ↓
Internal Review
   ├── needs revision ───────────┐
   │                             │
   └── approved                  │
          ↓                      │
Independent Validation           │
          ↓                      │
Promotion                        │
          ↓                      │
Learning                         │
          ↓                      │
Close / Complete Issue           │
                                 │
Development / Repair ◄───────────┘
```

### GitHub Issue authority

Before execution, Genesis synchronizes all open actionable repository Issues into its execution state and creates or reuses an Issue for every internally discovered task. Existing specialist capability/self-improvement Issues are reused rather than duplicated.

If GitHub Issue intake or Issue creation is unavailable, unbacked work fails closed. Genesis may preserve local evidence, but it may not dispatch or execute that task until Issue authority is restored.

Temporary unit-test task databases are explicitly excluded from real GitHub mutation so CI fixtures cannot create repository Issues accidentally.

### Discovery worker

Ranks Genesis source by evidence and risk, then confirms one concrete testable issue. Discovery may persist evidence locally, but the discovered work must be published as a GitHub Issue before Triage or implementation can execute it.

### Triage worker

Rejects protected targets, missing targets, weak-confidence findings, and invalid execution state. Accepted Issue-backed tasks move to the appropriate development/repair stage.

### Development / Repair worker

Uses the bounded Coding / DevLab candidate path. A successful candidate must pass the existing candidate Security review. The exact candidate is placed on an isolated review ref before independent validation.

### Review worker

Checks out the exact isolated candidate SHA, runs the full test suite again, and performs independent internal review against the Issue objective and diff. Its decision is either:

- `approve` → `validation_ready`
- `needs_repair` / `needs_development_revision` → the same Issue-backed task returns with review feedback

A candidate is never promoted merely because Genesis produced it.

### Validation worker

Does not validate its own work and does not promote code. The existing GitHub validation/promotion system retains independent validators, Security review, signed quorum, and promotion controls.

### Promotion observer

Observes whether the exact candidate or an equivalent safely rebased patch reached `main`. It has no direct-main write authority.

### Learning worker

Records the complete Issue/development/repair/review/promotion history as durable learning evidence, completes local execution state, and allows Genesis to continue with the next open Issue.

## Execution-state stages

```text
GitHub Issue
  → local bound state
      → discovered / assigned
          → development_ready / repair_ready
              → review_ready
                  → needs revision → development_ready / repair_ready
                  → validation_ready
                      → promoted
                          → closed / complete

invalid / exhausted work → quarantined, while the Issue remains the visible authoritative record
```

## Safety boundaries

The Issue-first architecture does not weaken Genesis's promotion trust model:

- no direct write to `main` by implementation workers;
- no autonomous edit of protected identity/security/control-plane files;
- no validation authority for Discovery, Triage, Development, Repair, Review, or Learning;
- candidate Security review remains mandatory;
- independent validators and signed quorum remain mandatory;
- exact reviewed candidate identity is preserved through handoffs;
- failed review returns evidence to the same Issue-backed work instead of weakening tests or validation;
- GitHub unavailability cannot silently restore SQLite as an independent task authority.

## Pulse behavior

Gene Pulse is the Issue-authoritative coordinator/wakeup boundary. Each real Pulse first imports open actionable Issues and binds any internally discovered work to Issues. One Pulse then performs at most one bounded specialist transition. A second Issue sync publishes tasks discovered during that Pulse before a later Pulse can execute them.

The persistent runtime uses the same Pulse boundary and requires a dedicated GitHub credential with the minimum repository permissions needed for Issue management. Without that credential, autonomous execution is intentionally blocked.
