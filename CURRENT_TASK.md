# Current Task — Genesis AI V0.1

Build the smallest executable **self-running Genesis node** with no dependency on Codex, ChatGPT, GitHub Copilot, Ollama, or any single AI provider.

## Required V0.1 components

1. Constitution verifier
   - load `GENESIS_CONSTITUTION.md`
   - compute SHA-256
   - compare with `GENESIS_BLOCK.json`
   - refuse canonical startup if verification fails

2. Autonomous runtime loop
   - start with `python -m genesis` or equivalent
   - run continuously while the host is online
   - maintain heartbeat and persistent state
   - recover safely after process or host restart
   - never require an interactive developer session to continue operating

3. Persistent state
   - lightweight local database
   - versioned schema
   - clear separation between trusted and candidate knowledge
   - store last successful cycle/checkpoint

4. Intelligence-provider interface
   - no mandatory Codex, Ollama, OpenAI, Google, DeepSeek, or other provider dependency
   - support pluggable local, remote, distributed, and future providers
   - if no intelligence provider is available, remain alive in maintenance/discovery mode rather than failing permanently

5. Bootstrap capability discovery
   - discover legally usable public/open intelligence providers and model artifacts through configurable adapters
   - record metadata, source, license, hash, hardware requirements, capabilities, and trust state
   - never execute an unverified downloaded model or binary directly

6. Model registry
   - states: discovered → quarantined → tested → validated → trusted → active
   - allow different models for different capabilities
   - models are replaceable capabilities, not Genesis AI's identity

7. Research and learning loop
   - accept user-contributed candidate knowledge
   - conduct self-directed public research through approved adapters
   - preserve provenance, evidence, confidence, contradictions, and validation state
   - never treat user or model output as automatically true

8. Evolution candidate system
   - propose improvements separately from stable code
   - run deterministic tests and policy checks before promotion
   - never self-promote solely because a model recommends a change
   - retain rollback information and audit trail

9. Audit log
   - append important events with timestamps and hashes
   - record provider/model selection, research ingestion, candidate creation, validation, and promotion decisions

10. Resource governor
   - configurable CPU, GPU, RAM, storage, bandwidth, research-frequency, and concurrency budgets
   - host owner retains control of local hardware resources

## Bootstrap principle

The first process does not need to begin as a frontier model. It must begin as a durable autonomous framework capable of staying alive, maintaining its Constitution and state, discovering available intelligence, evaluating it, and adding trusted capabilities over time.

## Non-goals for V0.1

- cryptocurrency/token issuance
- uncontrolled privileged self-replacement
- production medical advice or interventions
- large-scale consensus
- complete P2P networking
- blindly downloading or executing every public model
- dependency on a commercial coding agent

## Definition of done

A user can clone the repository and start one Genesis node. After startup, the node operates without Codex or another developer agent, verifies the canonical Constitution, persists its state, performs autonomous maintenance/discovery cycles, registers candidate intelligence resources, stores research/user learning with provenance, creates and evaluates candidate improvements, and records auditable results.
