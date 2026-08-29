# Genesis AI Network — TODO

This file is a **human-readable near-term backlog**. It is not the authority for autonomous execution.

> **Runtime source of truth:** Genesis autonomous work is controlled by the persistent task queue in `runtime/genesis_tasks.sqlite3`, together with validation and promotion rules. A Markdown checkbox must never directly authorize code promotion, release, model activation, or scientific validation.

## Immediate priorities

- [ ] Verify the first live generic Issue completes through claim, worker, independent validation, exact promotion and automatic closure after the autorepair recovery release.
- [ ] Complete the current proactive validation cycle for the capability-growth integration on `main`.
- [x] Bootstrap the Android mobile application under `mobile/` and produce the first test APK.
- [ ] Add production Android signing and a stable mobile release channel after alpha validation.
- [ ] Finish secure signed automatic-update support for Genesis Desktop.
- [ ] Add persistent Tauri updater signing keys through GitHub Secrets; never commit private signing material.
- [ ] Improve the Windows desktop UI with live Genesis Core status, Memory, Research, Coding, Security, Network and score views.
- [ ] Make desktop/mobile clients display the three-score system: AI Capability, Efficiency, and Immortality Research Progress.

## Intelligence, evaluation and experiments

- [x] Add Evaluation Module foundation with evidence-first scoring and zero credit for unmeasured capability.
- [x] Add Experiment Module foundation with baseline-versus-candidate keep/reject decisions.
- [x] Add Resource Module foundation for bounded CPU/memory/disk/battery/network capacity scoring.
- [x] Add Model Scout Module foundation with sequential discovered → quarantined → tested → validated → trusted → active lifecycle.
- [x] Feed measured provider outcome telemetry into Intelligence Router profiles after a minimum evidence threshold.
- [ ] Expand system-level benchmarks for reasoning, coding, research, tool use, long-horizon tasks and memory.
- [ ] Persist richer experiment hypotheses, baseline results, candidate results and decisions beyond provider telemetry.
- [ ] Add real local OS telemetry collection without requiring privileged access.
- [ ] Add model/provider discovery feeds with license verification and benchmark tournaments.
- [ ] Keep activation separate from discovery: no model becomes active without required validation evidence.

## Evidence, memory and learning

- [x] Add Evidence Module foundation with candidate/reviewed/validated/rejected/contradicted states.
- [ ] Add persistent evidence graph storage linking claims, sources, supporting evidence and contradictions.
- [ ] Connect research reviews and validated lessons to Evidence records.
- [ ] Add hierarchical memory compression for long-lived Genesis nodes.
- [ ] Add memory conflict detection and supersession/versioning.
- [ ] Improve retrieval using semantic similarity while keeping provenance and validation state visible.
- [ ] Convert validated successful strategies into procedural memory.

## GDEN / decentralization

- [x] Add Peer Compute Module foundation with bounded work leases and content-hash result verification.
- [ ] Implement peer task advertisement and capability discovery.
- [ ] Add owner-controlled resource offers/bids before remote task leasing.
- [ ] Transport signed work leases over authenticated GDEN peer connections.
- [ ] Require independent verification or reproducible checks before trusting peer-executed results.
- [ ] Design persistent independent validator identities and key rotation/revocation.
- [ ] Implement replicated state synchronization and conflict handling.
- [ ] Design Sybil resistance/reputation without requiring cryptocurrency initially.

## Applications

- [x] Publish a downloadable Android alpha APK with SHA-256 checksum.
- [ ] Add Android production signing; the current alpha is debug-signed for testing only.
- [ ] Add application build-health checks to the Application Module.
- [ ] Add application compatibility/version checks between Genesis Core and clients.
- [ ] Publish a stable Genesis Desktop release after alpha validation.
- [ ] Publish a stable Android release after security, signing and compatibility validation.

## Research mission

- [ ] Expand high-quality scientific source coverage for aging, regeneration, genomics, neuroscience, robotics and enabling technologies.
- [ ] Strengthen evidence grading and independent review of research findings.
- [ ] Track hypotheses, evidence, contradictions and experiments separately.
- [ ] Keep the Immortality Research Progress Score explicitly tied to evidence-pipeline maturity, not a percentage claim that physical immortality has been achieved.

## Product and sustainability

- [ ] Create a public status/download website using low-cost/free hosting first.
- [ ] Add opt-in telemetry only if privacy-preserving and explicitly user-controlled.
- [ ] Define a future Genesis Developer / hosted-node business model without making the open-source core dependent on paid services.

## Documentation rule

When an item becomes a real autonomous task, Genesis should create/update it in the persistent task queue. `TODO.md` may be synchronized for humans, but it must never be treated as signed operational state.
