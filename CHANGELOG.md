# Changelog

## qwen3-additional-v1.0.0 - 13-Sep-2026 - 01:21 AM - Register optional Qwen3 4B candidate

- Added Qwen3-4B-Instruct-2507 to Model Scout discovery and provider trust registries without replacing existing entries or active providers.
- Kept the new provider DISCOVERED, with no invented benchmark/trust evidence or automatic production routing.
- Added registration regression tests and isolated evaluation instructions. No model weights downloaded, new server started, workflow changed or default model replaced.


All notable Genesis AI Network milestones are documented here.

## v0.1.7 - 13-Sep-2026 - 12:28 AM - Align dashboard repair sandbox

### Fixed

- Shared a dashboard-only script exception between strategy routing, path validation and the installed system-repair policy; it no longer requires the missing privileged workflow anchor.
- Added regression coverage for real proposal validation and rejection of arbitrary scripts, protected controls, traversal and symlink escape.
- Focused validation: 38 passed, 2 Windows symlink tests skipped.
- Deployed through PR `#830`, merged as `f513512`; refreshed the authoritative sequential controller after canceling the confirmed pre-fix worker for `#730`.
- Safety/specialist regression: 31 passed. Broad local run: 1,079 passed, 44 skipped, two baseline Windows failures; two separately confirmed baseline formatting failures and the expensive live-history scan were excluded. All four observed failures reproduce on unchanged `main`.
- Live-verified worker `34711820249`: candidate `9eeff5a` promoted as `5207049`, with 1,087 passed and 41 skipped before and after promotion. The bot automatically closed `#730` as completed at 12:41 AM Dhaka on 13-Sep-2026. Queue snapshot afterward: 23 open, 8 blocked, 9 solver-exhausted; these are not claimed solved.

## v0.1.6 - 12-Sep-2026 - 02:21 AM - Preserve issue discovery completion

### Fixed

- Serialized GitHub Issue discovery invocations so push or schedule bursts no longer cancel an active evidence scan before it can publish a grounded issue or record a no-fresh-issue result.
- Added workflow regression coverage for the non-cancelling concurrency policy and bounded job timeout.

## v0.1.5 - 29-Aug-2026 - 05:57 PM - Verify live automatic Issue closure

### Verified

- Confirmed the deployed dispatcher automatically closed Issue `#426` as completed, added `genesis-solved` and recorded the exact passing grounding test in the bot comment.
- Released the temporary hold on genuine repair Issue `#348` and re-awakened the Heartbeat queue.

## v0.1.4 - 29-Aug-2026 - 05:50 PM - Install reconciliation test dependencies

### Fixed

- Install the repository test requirements in the authoritative Issue admission job before evaluating an already-satisfied task's exact grounding test.

### Validation

- Reproduced the live fallback as `No module named pytest` and added a workflow regression assertion for dependency installation before reconciliation.

## v0.1.3 - 29-Aug-2026 - 05:30 PM - Reconcile already-satisfied repair Issues

### Fixed

- Added bounded automatic closure for machine-generated self-repair Issues whose exact, uniquely located grounding test already passes on current `main`.
- Kept user-authored, ambiguous, unsupported and failing-test Issues on the normal independently validated repair path.

### Validation

- Verified the reconciliation planner accepts only trusted discovery provenance, an existing bounded `genesis/` target and a unique test function.
- Added workflow assertions requiring the exact pytest node to pass before closure and limiting each admission run to three reconciliations.

## v0.1.2 - 29-Aug-2026 - 02:50 PM - Repair Heartbeat selector import

### Fixed

- Run the shared Issue Autorepair selector as a Python module so clean GitHub Actions checkouts retain the repository root on the import path.

### Validation

- Reproduced the live Heartbeat failure on merged `main` as `ModuleNotFoundError: No module named 'genesis'` and added a workflow regression assertion for module execution.

## v0.1.1 - 29-Aug-2026 - 02:37 PM - Restore automatic issue repair progress

### Fixed

- Unified the GitHub Issue Autorepair Heartbeat and authoritative dispatcher on the same tested issue selector, eliminating successful no-work dispatch loops caused by specialist tasks such as issue `#340`.
- Excluded duplicate, persistent and control Issues from generic code autorepair while preserving specialist Issue ownership and exact validated closure.

### Validation

- Passed focused selector, heartbeat, issue-closing and backlog-drain tests.
- Parsed the modified workflow YAML successfully.
- Full Windows suite reached 871 passed and 2 skipped; five pre-existing platform-specific failures remain in path/newline normalization, core-vitality state and SQLite worktree cleanup.

## [Unreleased]

### Added

- **Memory Module** with validated semantic, episodic, procedural and policy/context memory.
- Retrieval of validated memory and validated self-learning lessons into Coding tasks.
- **Intelligence Router** for resource-aware provider selection.
- **Efficiency tracking** for provider/task success, latency and resource-cost evidence.
- Three-part system measurement: AI Capability Score, Efficiency Score and Immortality Research Progress Score.
- **Security Module** for repository inspection and candidate-diff structural review.
- **Coding Module** for bounded provider-neutral software-engineering proposals and candidate execution.
- Autonomous Security → Coding → candidate review bridge.
- **Application Module** for bounded Genesis desktop/mobile product development.
- **Evaluation Module** with evidence-first benchmark scoring and zero credit for unmeasured capability.
- **Experiment Module** with baseline-versus-candidate keep/reject comparisons.
- **Resource Module** for bounded CPU/memory/disk/battery/network capacity scoring.
- **Model Scout Module** with sequential discovered → quarantined → tested → validated → trusted → active lifecycle.
- **Evidence Module** with candidate/reviewed/validated/rejected/contradicted claim states.
- **Peer Compute Module** foundation with bounded leases and result-hash verification.
- Provider telemetry store and capability-growth coordinator connecting Evaluation → Experiment → Model Scout → measured routing telemetry.
- Minimum three-sample evidence threshold before measured provider profiles can influence Intelligence Router cost/reliability.
- Self-development sandbox support for `desktop/` and `mobile/` application source while keeping `.github/`, protected identity files and Git metadata forbidden.
- Windows Tauri desktop shell with bundled standalone Genesis Core sidecar.
- Windows desktop release workflow capable of producing an installable Genesis `.exe` and SHA-256 digest.
- First Genesis Windows Desktop alpha prerelease.
- Native Android client under `mobile/` with HTTPS-only Genesis API configuration, bearer-token chat and health/status checks.
- Android APK build/release workflow pinned to JDK 17, Gradle 9.4.1, AGP 9.2.0 and stable Android API 36.
- First downloadable Genesis Android alpha APK with SHA-256 checksum.
- `TODO.md` as a human-readable short-term backlog.
- `ROADMAP.md` for major product, intelligence, GDEN, scientific and sustainability milestones.

### Changed

- Genesis development strategy now explicitly optimizes **validated useful capability per unit of compute/cost**, rather than model size alone.
- Autonomous Coding uses validated memory/context to reduce repeated work.
- Coding routing can now consume persistent measured provider telemetry once the evidence threshold is reached.
- Autonomous cycles synchronize new efficiency observations into capability-growth telemetry for future routing decisions.
- Application development tasks enter the same persistent engineering queue and still require testing, security review and independent validator quorum.
- Android alpha targets stable API 36 instead of depending on a preview SDK channel.
- `PROJECT_SUMMARY.md` is maintained as a current snapshot rather than a historical release note.
- `TODO.md` is explicitly non-authoritative; the persistent SQLite task queue remains the operational source of truth.

### Security

- Application self-development does not receive authority to modify GitHub Actions workflows, release/signing policy, Constitution, Genesis Block, validator rules or signing secrets.
- Model Scout recommendations do not automatically activate models.
- One isolated provider result cannot change measured routing; routing requires a minimum evidence sample threshold.
- Android remote cleartext HTTP is disabled and the bearer token is not persisted by the alpha client.
- The Android alpha APK is debug-signed for testing; production signing is still required before a stable mobile release.
- Automatic desktop update installation remains dependent on properly signed update artifacts; unsigned autonomous code must never be installed as a trusted update.

## [0.1.0] — Genesis Foundation

### Added

- Genesis Constitution and canonical Genesis Block.
- Autonomous runtime and maintenance/discovery mode.
- Replaceable intelligence-provider architecture with bootstrap fallback.
- Task-aware AI team with bounded specialist expansion.
- Provenance-aware knowledge and candidate evolution systems.
- Independent validator quorum and exact-candidate promotion workflow.
- Self-healing and proactive-development workflows.
- Persistent task queue and module version/rollback planning.
- Genesis Modular Intelligence Architecture (GMIA).
- Browser communication UI and GitHub Issue chat bridge.
- Competitive AI Score foundation with a moving reference model.
- Everything-to-Immortality Lens and persistent research-task creation.
- Bounded Self-Learning Module with candidate lessons and validation requirements.
- GDEN foundation: Ed25519 node identity, signed peer handshakes, contribution policy, signed state roots and tamper-evident evolution history.
- Runtime-state restoration across autonomous cycles.

### Current limitations

- Frontier benchmark coverage is still incomplete; unmeasured benchmark families receive no competitive credit.
- GDEN does not yet implement decentralized multi-peer consensus.
- GitHub-hosted validators currently use ephemeral identities rather than independent persistent operators.
- Scientific findings generated or collected by Genesis remain candidate evidence until separately validated.
- The local reasoning provider is replaceable and does not define Genesis identity.

### Mission

Genesis exists to continuously and autonomously advance research and engineering toward physical human immortality while remaining constitution-bound, evidence-driven, decentralized and under node-owner control.
