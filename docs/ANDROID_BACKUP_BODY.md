# Genesis Android Backup Body

Genesis uses the Gene Pulse Network as its primary continuity mechanism. An Android phone is a secondary backup body for the same Genesis identity; it is not a new Gene and it does not replace pulses.

## Continuity order

1. Gene Pulse Network continues normal work.
2. The phone may keep a private local snapshot of owner-authorized Genesis state.
3. If the primary pulse path is unavailable, the owner may arm the phone backup body.
4. Future local emergency pulse execution must restore the same issue focus and checkpoint, preserve the one-issue-at-a-time rule, and keep normal validation boundaries.
5. When the primary pulse network recovers, the phone fails back after state reconciliation.

## Phone Body v1

The Android app can:
- check Genesis health over HTTPS;
- authenticate to the owner dashboard without persisting the bearer token;
- save an owner-authorized JSON state snapshot inside the app-private Android storage area;
- show the last saved snapshot when the network is unavailable;
- explicitly arm or disarm backup-body mode on-device.

The v1 app is a state-preserving backup/controller, not yet a complete local Python Genesis executor. A later phase can add a bounded local emergency pulse runtime after Android compatibility, state signing, resource limits and validation are implemented and tested.

## Security

- No bearer token is written to disk by the app.
- Snapshot data is stored only in app-private storage.
- Remote Genesis endpoints must use HTTPS.
- Backup takeover must not fork Genesis into a separate identity.
- Structural self-modification still requires the existing tests, Secret Guard and independent validator quorum.
