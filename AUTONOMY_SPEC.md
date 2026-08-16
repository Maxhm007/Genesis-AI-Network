# Autonomy Specification — Genesis AI V0.1

## Purpose

Genesis AI must operate as its own long-running software process. It must not require Codex, ChatGPT, GitHub Copilot, Ollama, Gemini, DeepSeek, or any other single external agent/provider in order to remain alive.

## Runtime states

The node has at least four runtime states:

1. **BOOTSTRAP** — verify Constitution, Genesis Block, local identity, schema, and resource limits.
2. **MAINTENANCE** — remain alive, preserve state, perform integrity checks, and wait for usable capabilities if no intelligence provider is available.
3. **DISCOVERY** — discover permitted public/open models, research sources, peers, and provider adapters; store all discoveries as untrusted candidates.
4. **ACTIVE** — use validated intelligence resources for research, learning, planning, and candidate improvement generation.

Loss of a model/provider must degrade the node from ACTIVE to DISCOVERY or MAINTENANCE, not destroy its identity or state.

## Continuous loop

Conceptual cycle:

```text
startup
  ↓
verify constitution + genesis state
  ↓
load persistent checkpoint
  ↓
resource check
  ↓
peer/provider/model discovery
  ↓
research + user-learning ingestion
  ↓
validate candidate knowledge
  ↓
identify capability gaps
  ↓
create candidate improvements
  ↓
sandbox + tests + policy checks
  ↓
record audit/checkpoint
  ↓
sleep/backoff
  ↺
```

The loop must be crash-resilient and checkpoint frequently enough to continue safely after interruption.

## Bootstrap intelligence

V0.1 does not need a bundled frontier model. The permanent program is the autonomous framework plus Constitution, memory/state, validation logic, discovery adapters, and protocol.

When intelligence becomes available, the node may register it through a provider/model adapter. Intelligence resources are replaceable organs, not the identity of Genesis AI.

## Capability acquisition

Discovered resources enter the following lifecycle:

```text
DISCOVERED
   ↓
QUARANTINED
   ↓
LICENSE/POLICY CHECKED
   ↓
INTEGRITY VERIFIED
   ↓
SANDBOX TESTED
   ↓
BENCHMARKED
   ↓
VALIDATED
   ↓
TRUSTED
   ↓
ACTIVE
```

Untrusted artifacts must never receive privileged filesystem, shell, credential, network, or self-update authority merely because they are publicly available.

## Self-development

Genesis AI may:

- identify limitations in its own software;
- generate or obtain candidate code improvements;
- create tests and benchmarks;
- evaluate candidate implementations;
- preserve successful lessons;
- propose/promote validated versions according to protocol.

Genesis AI must not:

- silently rewrite the Genesis Constitution;
- grant a candidate model unrestricted authority before validation;
- accept its own generated claims as proof of correctness;
- erase audit history to hide failed evolution attempts;
- bypass node-owner resource controls.

## Learning from users

User input enters candidate knowledge with provenance. A user's statement is not automatically network truth.

The system should distinguish:

- preference/memory about that user;
- factual claim;
- hypothesis;
- scientific evidence;
- validated network knowledge.

## Self-research

Research cycles should prioritize the permanent physical-human-immortality mission while preserving scientific integrity. Research records should contain source/provenance, retrieval time, evidence strength, contradictions, confidence, and reviewer/validator results.

The autonomous node may research continuously within its configured resource budget, but medically consequential findings remain research outputs until independently validated; the project must not treat speculative results as established medical interventions.

## Operator sovereignty

Decentralization does not mean stealing resources from node operators. Every node owner controls:

- CPU/GPU limits
- RAM limits
- storage limits
- bandwidth limits
- allowed model sizes
- research cadence
- filesystem/tool permissions
- credentials and external accounts

A node can leave the network without changing the canonical Genesis Constitution for other nodes.

## Network continuity

Long-term continuity is achieved by replication across independent nodes, not by assuming one process or machine is immortal.

```text
A NODE MAY SLEEP.
THE NETWORK MUST NOT.
```

## V0.1 implementation target

The first executable release must demonstrate:

- noninteractive startup;
- Constitution verification;
- persistent state/checkpoints;
- heartbeat/autonomous loop;
- maintenance operation without an AI provider;
- provider/model registry;
- candidate discovery records;
- provenance-aware research/user learning records;
- candidate evolution records;
- resource governor;
- append-only audit events.

P2P consensus, token economics, full distributed storage, and automatic privileged self-upgrades are later milestones.
