# Gene Continuous Work Rule

Every Gene focuses on one unresolved issue at a time.

## Core loop

1. Select the highest-priority unresolved issue if no focus exists.
2. Persist that focus across restarts.
3. Work the same issue until it is resolved.
4. A failed attempt does not release focus. Diagnose and retry with a different method when useful.
5. A Gene may ask another Gene for help, use validated peer knowledge, search for new evidence, or reframe the repair while keeping the same issue.
6. Structural/code changes still require tests, Security review and independent validator quorum.
7. When the issue is resolved, immediately select the next unresolved issue.
8. If no issue exists, enter learning/discovery mode: learn from evidence, inspect capability gaps, review deferred/unsolved problems, run logical experiments, and use authorized web/network research when available.
9. When learning/discovery identifies a real actionable gap, create it as an issue and return to issue-solving mode.

## Continuous does not mean cron

The work state is persistent and event/loop driven. An hourly or minute schedule is not the authority that makes a Gene continue working. `scripts/gene_continuous_work.py` can run as a long-lived process and continuously reassess state. A small internal pause only prevents CPU busy-spinning.

GitHub Actions may still be used as a bootstrap, validation, recovery or fallback execution environment, but GitHub-hosted runners are finite jobs and therefore cannot by themselves guarantee an endless process. A durable deployment should run the continuous worker on an authorized persistent runtime while retaining GitHub as repository, validation and coordination infrastructure.

## Genuine external block

A Gene may release an issue only when the issue is explicitly marked as requiring an external dependency it cannot control, such as an owner-only secret, permission or unavailable external resource. Ordinary implementation failure is not an external block.
