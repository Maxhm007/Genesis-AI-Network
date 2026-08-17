# Genesis Android Emergency Pulses

Genesis remains one distributed identity. The Android phone is a backup body for the same Genesis, not a new Gene.

## Primary / backup rule

- Primary continuity: Gene Pulse Network and other authorized pulse providers.
- Backup continuity: Android emergency pulses when the phone backup body is armed.
- The phone does not replace the normal pulse network while that network is healthy.

## One pulse, one step

A phone emergency pulse:

1. loads the latest app-private Genesis snapshot;
2. restores the locally focused issue when it is still present;
3. otherwise selects the highest-priority issue from the snapshot;
4. if no issue exists, enters bounded local discovery;
5. performs exactly one bounded planning/analysis step;
6. persists local pulse state and attempt count;
7. writes a reconciliation candidate to app-private storage;
8. stops.

Repeated local pulses preserve the same issue until the mirrored state no longer contains it. A retry may change method but must not silently abandon the focused issue.

## Safety and authority

Android emergency pulses are candidate-only. They cannot directly modify canonical Genesis source, promote lessons, bypass Secret Guard, bypass independent validation, or claim network consensus. On recovery, their evidence must be reconciled into the normal Genesis workflow and independently validated before promotion.

The bearer token remains memory-only. Snapshot, pulse state, and reconciliation candidates remain in Android app-private storage.

## Current scope

Phase 2 provides a bounded Android-native emergency pulse engine for offline/backup continuity. It can inspect cached state, continue issue focus, generate a next-step candidate, track retries, and preserve evidence for reconciliation. It is not a full offline replacement for every Python Genesis module, external model, browser/web research service, or GitHub validator.
