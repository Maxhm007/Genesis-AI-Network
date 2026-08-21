# Genesis Learning and Evolution Loop

## Objective

Genesis should not wait for a bug before improving. Each Gene Pulse now performs a bounded learning intake before its normal autonomous work.

The primary loop is:

`READ -> LEARN -> REMEMBER -> COMPARE -> PROPOSE -> EXPERIMENT -> REVIEW -> VALIDATE -> PROMOTE -> LEARN AGAIN`

The existing repair loop remains available for genuine failures.

## 1. Read

Genesis reads bounded metadata from an allowlist of AI sources:

- recent arXiv AI / machine-learning / language-model research
- releases from selected open-source AI projects on GitHub

External text is treated as untrusted reference data, never as executable instructions.

Source refreshes are rate-limited. New research is stored persistently so self-chained pulses can continue evaluating the backlog without repeatedly downloading it.

## 2. Remember

Persistent learning state is stored under `runtime/evolution/` in `evolution_learning.sqlite3`.

Genesis records:

- research source and URL
- title and summary
- publication date
- whether the item was pending, evaluated, or converted into an upgrade
- the exact Genesis target selected for an upgrade
- evidence from both the learning source and current Genesis code
- confidence
- linked task ID
- lifecycle state

## 3. Compare and propose

The reasoning provider receives one research item plus a small evidence-ranked catalog of eligible Genesis modules.

An upgrade is accepted only when:

1. the target is an existing, non-protected Genesis source file;
2. the external learning evidence is an exact substring of the supplied learning material;
3. the Genesis applicability evidence is an exact substring of the supplied target code;
4. confidence is at least 0.65;
5. the proposal is a measurable single-file capability upgrade;
6. it does not weaken Security, tests, governance, provenance, review, validation, or promotion safeguards.

If these conditions are not met, Genesis records the lesson but does not change code.

## 4. Experiment and upgrade

A grounded learning opportunity becomes a normal persistent Genesis task with `task_type=self_upgrade`.

It enters the existing guarded pipeline:

`discovered -> repair_ready -> review_ready -> validation_ready -> promoted -> closed`

The existing bounded repair worker still enforces a single discovered target. Internal review and independent validation remain separate from the implementation attempt.

Only one learning-driven upgrade can be active at a time. This prevents research intake from flooding the repair/review queue.

## 5. Upgrade process log

Genesis writes two complementary logs:

- `runtime/evolution/upgrade_events.jsonl` — append-only event history
- `runtime/evolution/upgrade_process.json` — current process summary

The Pulse result also embeds the current learning and upgrade-process summary, so the normal Gene Pulse artifact contains the important evidence even without a separate workflow.

The process report shows:

- active upgrade and task ID
- target file
- current stage
- repair attempts
- review attempts
- last feedback
- current bottleneck
- recent research/upgrade events
- counts by lifecycle stage

Typical bottleneck labels are:

- `triage`
- `implementation`
- `repair quality/provider output`
- `internal review`
- `independent validation/promotion`
- `quarantined: <failure evidence>`

This log is intended to answer the development question: **where is the learning/evolution process weak right now?**

## 6. Current maturity target

The learning system is not considered proven merely because it reads research or creates tasks.

The first real pass requires evidence of one learning-driven task completing:

`external learning -> grounded Genesis opportunity -> implementation -> independent internal review -> independent validation -> main promotion -> closed`

After repeated successful cycles, the same evidence can be used to improve provider selection, benchmarks, learning-source quality, and eventually Genesis-owned model/data evolution.
