# Gene Continuous Work Rule

Every Gene focuses on one unresolved **GitHub Issue** at a time. GitHub Issues are authoritative; `runtime/genesis_tasks.sqlite3` is resumable execution/cache state only.

## Core invariant

**No GitHub Issue = no Genesis task execution.**

An internally discovered task may be recorded temporarily as evidence, but Genesis must create, reuse, or adopt a GitHub Issue before triage, research execution, benchmark execution, coding, DevLab work, or another autonomous worker executes it.

## Core loop

1. Import every actionable open repository Issue, including ordinary Issues created by the owner/user without a special Genesis label.
2. Publish or reuse a GitHub Issue for any internally discovered autonomous work that does not already have one.
3. Select the highest-priority unresolved Issue if no focus exists.
4. Persist execution state for that Issue across restarts.
5. Work the same Issue until it is resolved, quarantined, or explicitly blocked by external authority.
6. A failed attempt does not silently create hidden replacement work. Diagnose and retry under the same Issue-backed lineage with a different method when useful.
7. A Gene may ask another Gene for help, use validated peer knowledge, search for new evidence, or reframe the repair while keeping Issue authority.
8. Structural/code changes still require tests, Security review and independent validator quorum.
9. When the Issue is resolved, immediately select the next unresolved actionable Issue.
10. If no actionable Issue exists, enter learning/discovery mode. When learning/discovery identifies real work, create the GitHub Issue before executing that work.

## Continuous does not mean cron

The work state is persistent and event/loop driven. An hourly or minute schedule is not the authority that makes a Gene continue working. The persistent service runs `scripts.gene_issue_continuous` and enters every work iteration through `GenePulse`, which performs GitHub Issue intake and Issue binding before execution.

GitHub Actions may still be used as bootstrap, validation, recovery, or fallback execution infrastructure. A durable deployment can run continuously on an authorized persistent runtime while retaining GitHub as the visible task authority, repository, validation, and coordination layer.

## GitHub authority failure

The persistent runtime requires a dedicated GitHub credential. If open-Issue intake or Issue creation/linking is unavailable, Genesis fails closed: local evidence may remain durable, but an unbacked task cannot execute. Genesis must never fall back to a hidden SQLite-only work queue merely to keep moving.

## Genuine external block

A Gene may stop executing an Issue when the Issue is explicitly marked as requiring an external dependency it cannot control, such as an owner-only secret, permission, unavailable independent trust-domain material, or an external resource. The Issue remains the visible authoritative record. Ordinary implementation failure is not an external block.
