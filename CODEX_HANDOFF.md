# Codex Handoff

Read this file together with `GENESIS_CONSTITUTION.md`, `NETWORK_SPEC.md`, `MODEL_POLICY.md`, `KNOWLEDGE_POLICY.md`, `DISTRIBUTION_PROTOCOL.md`, and `CURRENT_TASK.md` before making changes.

## Project intent

Build Genesis AI as a decentralized, self-improving scientific AI system dedicated permanently to physical human immortality, bounded by the immutable Genesis Constitution.

## Current architectural decisions

- Do not make Ollama mandatory in V0.1.
- Use an intelligence-provider abstraction so models/providers remain replaceable.
- Treat models as capabilities, not identity.
- Learning from users creates candidate knowledge, not automatic truth.
- Publicly available models must pass license, quarantine, benchmark, security, and constitution checks.
- AI-generated code must not directly overwrite stable production code.
- Evolution follows candidate → sandbox → test → review → validate → signed release.
- Large models and datasets remain off-chain; hashes and compact commitments go on-chain.
- Repository/storage location does not define authenticity; cryptographic verification does.
- The long-term system must support P2P nodes, replicated state, distributed storage, and continuous network presence.

## Coding guidance

Prefer small, auditable modules with explicit interfaces. Avoid premature blockchain complexity, token economics, or autonomous privileged self-modification in V0.1.

Before coding:

1. inspect all project specification files;
2. summarize your understanding;
3. identify contradictions or missing decisions;
4. propose the smallest implementation plan;
5. preserve the Genesis Constitution exactly.
