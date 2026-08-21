# Genesis Learning Waiting Queue

Genesis research learning is non-blocking. A slow or failed research item must not prevent later items from being evaluated.

State flow:

`pending -> processing -> evaluated|enqueued`

On assessment failure:

`processing -> waiting -> pending` after the retry delay.

After the bounded retry budget is exhausted:

`processing -> quarantined`.

Current defaults:

- At most 2 research claims per Gene Pulse.
- Retry delays start at 10 minutes and use bounded exponential backoff.
- 3 failed assessments quarantine the research item.
- A processing lease older than 20 minutes is recovered so a crashed run cannot leave an item stuck forever.
- When one item moves to waiting or quarantine, the same Pulse may immediately claim the next ready item.
- Queue counts and the next retry time are included in the evolution progress report.

This queue controls research assessment only. A grounded upgrade still enters the existing guarded engineering pipeline for triage, repair, review, independent validation, and promotion.
