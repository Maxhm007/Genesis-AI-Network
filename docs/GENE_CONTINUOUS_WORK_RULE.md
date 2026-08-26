# Gene Continuous Work Rule

Every Gene focuses on one unresolved **GitHub Issue** at a time. GitHub Issues are authoritative; `runtime/genesis_tasks.sqlite3` is resumable execution/cache state only.

## Core invariant

**No GitHub Issue = no Genesis task execution.**

An internally discovered task may be recorded temporarily as evidence, but Genesis must create, reuse, or adopt a GitHub Issue before triage, research execution, benchmark execution, coding, DevLab work, or another autonomous worker executes it.

## Core loop

1. Import every actionable open repository Issue, including ordinary Issues created by the owner/user without a special Genesis label.
2. Publish or reuse a GitHub Issue for any internally discovered autonomous work that does not already have one.
3. Select the highest-priority unresolved Issue if no focus exists.
4. Persist execution state for that Issue across GitHub Actions runs.
5. Work the same Issue until it is resolved, quarantined, or explicitly blocked by external authority.
6. A failed attempt does not silently create hidden replacement work. Diagnose and retry under the same Issue-backed lineage with a different method when useful.
7. A Gene may ask another Gene for help, use validated peer knowledge, search for new evidence, or reframe the repair while keeping Issue authority.
8. Structural/code changes still require tests, Security review and independent validator quorum.
9. When the Issue is resolved, immediately select the next unresolved actionable Issue.
10. If no actionable Issue exists, enter learning/discovery mode. When learning/discovery identifies real work, create the GitHub Issue before executing that work.

## Production continuous runtime

GitHub Actions is the production continuous runtime. Genesis does not require an external SSH host, systemd service, paid VPS, or always-on server to continue autonomous work.

The production loop is:

`Actions heartbeat → Gene Pulse → optional coding-intelligence Pulse → persisted runtime cache/artifacts → next bounded Pulse`

The Gene Pulse restores the latest persisted `runtime/` state, performs GitHub Issue intake and Issue binding before execution, advances one bounded transition, saves runtime state again, and requests the next Pulse when more work remains. Provider-bound coding work is delegated to the coding-intelligence Pulse and then returns to the normal Gene Pulse chain.

The **Genesis Autonomy Heartbeat** runs every 15 minutes as a recovery mechanism. It does not create a second task system. It checks whether a fresh autonomous worker is already active and only dispatches a new Gene Pulse when the chain is idle. Concurrency controls prevent duplicate Pulse execution for the same Gene.

Scheduled proactive development may still run independently for broader research, learning, monitoring, and validated candidate generation, but GitHub Issues remain the authoritative production task source.

## Runtime persistence

GitHub-hosted runners are ephemeral, so Genesis persists continuity through GitHub Actions cache and artifacts rather than a permanent machine filesystem. The runtime SQLite database remains execution/cache state only and is restored between bounded Pulse generations.

A missing cache may cause Genesis to rebuild execution state from visible repository/GitHub Issue authority, but it must never convert SQLite into an independent hidden source of executable tasks.

## GitHub authority credentials

Gene Pulse and coding-intelligence Pulse use the workflow-scoped `github.token` with explicit `issues: write` permission for Issue intake, creation, adoption, and status synchronization. No external runtime credential is required for the production Actions path.

If open-Issue intake or Issue creation/linking is unavailable, Genesis fails closed: local evidence may remain durable, but an unbacked task cannot execute. Genesis must never fall back to a hidden SQLite-only work queue merely to keep moving.

## Genuine external block

A Gene may stop executing an Issue when the Issue is explicitly marked as requiring an external dependency it cannot control, such as an owner-only secret, permission, unavailable independent trust-domain material, or an external resource. The Issue remains the visible authoritative record. Ordinary implementation failure is not an external block.
