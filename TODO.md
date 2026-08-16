# Genesis AI Network — TODO

This file is a **human-readable near-term backlog**. It is not the authority for autonomous execution.

> **Runtime source of truth:** Genesis autonomous work is controlled by the persistent task queue in `runtime/genesis_tasks.sqlite3`, together with validation and promotion rules. A Markdown checkbox must never directly authorize code promotion, release, model activation, or scientific validation.

## Immediate priorities

- [ ] Validate the current Application Module integration on the latest `main` head.
- [ ] Bootstrap the Android mobile application under `mobile/` and produce the first test APK.
- [ ] Finish secure signed automatic-update support for Genesis Desktop.
- [ ] Add persistent Tauri updater signing keys through GitHub Secrets; never commit private signing material.
- [ ] Improve the Windows desktop UI with live Genesis Core status, Memory, Research, Coding, Security, Network and score views.
- [ ] Make desktop/mobile clients display the three-score system: AI Capability, Efficiency, and Immortality Research Progress.
- [ ] Add application build-health checks to the Application Module.
- [ ] Add application compatibility/version checks between Genesis Core and clients.

## Intelligence and efficiency

- [ ] Expand system-level benchmarks for reasoning, coding, research, tool use, long-horizon tasks and memory.
- [ ] Measure capability per compute unit and capability per dollar using real task outcomes.
- [ ] Improve Intelligence Router provider selection using observed quality, latency, resource cost and task type.
- [ ] Add automatic model discovery → quarantine → benchmark → validation → activation workflow.
- [ ] Keep unmeasured capabilities at zero evidence credit rather than estimating them optimistically.

## Memory and learning

- [ ] Add hierarchical memory compression for long-lived Genesis nodes.
- [ ] Add memory conflict detection and supersession/versioning.
- [ ] Improve retrieval using semantic similarity while keeping provenance and validation state visible.
- [ ] Convert validated successful strategies into procedural memory.
- [ ] Prevent candidate/unvalidated memories from entering normal trusted reasoning by default.

## GDEN / decentralization

- [ ] Implement peer task advertisement and capability discovery.
- [ ] Add bounded remote task leasing with owner-controlled resource policy.
- [ ] Add result verification, hashes and provenance for peer-executed work.
- [ ] Design persistent independent validator identities and key rotation/revocation.
- [ ] Implement replicated state synchronization and conflict handling.
- [ ] Design Sybil resistance/reputation without requiring cryptocurrency initially.

## Research mission

- [ ] Expand high-quality scientific source coverage for aging, regeneration, genomics, neuroscience, robotics and enabling technologies.
- [ ] Strengthen evidence grading and independent review of research findings.
- [ ] Track hypotheses, evidence, contradictions and experiments separately.
- [ ] Keep the Immortality Research Progress Score explicitly tied to evidence-pipeline maturity, not a percentage claim that physical immortality has been achieved.

## Product and sustainability

- [ ] Publish a stable Genesis Desktop release after alpha validation.
- [ ] Publish a downloadable Android APK after security/build validation.
- [ ] Create a public status/download website using low-cost/free hosting first.
- [ ] Add opt-in telemetry only if privacy-preserving and explicitly user-controlled.
- [ ] Define a future Genesis Developer / hosted-node business model without making the open-source core dependent on paid services.

## Documentation rule

When an item becomes a real autonomous task, Genesis should create/update it in the persistent task queue. `TODO.md` may be synchronized for humans, but it must never be treated as signed operational state.
