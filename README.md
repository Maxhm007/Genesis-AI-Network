# Genesis AI Network

> **Decentralized, autonomous scientific AI focused on the long-term mission of physical human immortality.**

[![Independent Validator Gate](https://github.com/Maxhm007/Genesis-AI-Network/actions/workflows/independent-validator-gate.yml/badge.svg)](https://github.com/Maxhm007/Genesis-AI-Network/actions/workflows/independent-validator-gate.yml)
[![Proactive Development](https://github.com/Maxhm007/Genesis-AI-Network/actions/workflows/proactive-development.yml/badge.svg)](https://github.com/Maxhm007/Genesis-AI-Network/actions/workflows/proactive-development.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Current release:** `v0.1.0 — Genesis Foundation`

Genesis AI Network is an open-source experimental AI system whose permanent mission is:

> **Enable humans who choose it to maintain continuous physical life, health, identity, cognition and bodily function indefinitely, ultimately eliminating involuntary death caused by aging, disease and physical deterioration.**

Genesis is not one model. Models are replaceable. Code is evolvable. Knowledge is expandable. The mission and constitutional constraints are permanent.

## Why Genesis exists

Genesis is being built as a continuously operating research and development network rather than a single chatbot or model. It is designed to:

- search for scientific and cross-domain developments relevant to physical human immortality;
- turn useful discoveries into persistent research tasks;
- learn from validated experience without treating generated guesses as truth;
- measure itself against a moving competitive-AI benchmark reference;
- identify capability gaps and create bounded candidate improvements;
- validate software changes before promotion;
- operate through replaceable intelligence providers;
- evolve toward a peer-to-peer decentralized network where independent Genesis nodes can contribute resources, validation and knowledge.

## Architecture

```text
                    Genesis Constitution
                           │
                    Genesis Identity
                           │
                 Modular Genesis Runtime
                           │
     ┌──────────────┬──────┴──────┬──────────────┐
     │              │             │              │
 Research      Self-Learning   Self-Dev        GDEN
     │              │             │              │
 Immortality    Candidate      Candidate      P2P identity
    Lens          Lessons        Code        + signed state
     │              │             │              │
     └──────────────┴──────┬──────┴──────────────┘
                           │
                  Independent Validation
                           │
                     Validated State
```

## What works today

Genesis currently includes:

- **Constitution verification** and a canonical Genesis Block.
- **Continuous proactive workflow** with scheduled research and development cycles.
- **Replaceable reasoning providers**, with a bootstrap fallback and a validated local Qwen provider path.
- **Task-aware multi-agent orchestration** for research, engineering, review, validation and network work.
- **Everything-to-Immortality Lens** that evaluates developments as direct, indirect, speculative or unknown rather than forcing unsupported connections.
- **Persistent research tasks** and bounded research review.
- **Self-Learning Module** that records candidate lessons with provenance and requires validation before treating them as trusted knowledge.
- **Competitive AI Score** that creates update pressure when Genesis is below its configured moving frontier reference. Unmeasured frontier abilities receive no frontier credit.
- **Candidate → test → independent validator quorum → promotion** software evolution.
- **Cryptographic GDEN node identity**, signed peer handshakes, owner-controlled contribution policy and tamper-evident evolution history.
- **Persistent runtime-state restoration** between autonomous cycles.

## Competitive AI Score

Genesis does **not** award itself a high score merely because its software is healthy.

The score is a moving engineering measure against configured frontier benchmark families plus autonomy, research, decentralization and validation.

- Low score → high development pressure.
- Unmeasured benchmark family → little or no competitive credit.
- Score increases only from recorded evidence.
- `99/100` is reserved for broadly verified frontier-or-better performance across the defined benchmark suite plus continuous autonomy, research, resilience and safety.
- `100/100` is intentionally not assigned.

This is **not** a consciousness score and is not proof of superiority to every human in every domain.

## Self-learning

Genesis self-learning is deliberately bounded:

```text
Experience / Research / Benchmark / Failure / Peer Feedback
                         ↓
                     Observation
                         ↓
                  Candidate Lesson
                         ↓
              Provenance + Confidence
                         ↓
                 Independent Review
                    ↓          ↓
                Validate     Reject
                    ↓
               Trusted Memory
```

The system must not promote its own generated statement into validated scientific knowledge simply because a model produced it.

## Decentralized evolution — GDEN

**GDEN** stands for **Genesis Decentralized Evolution Network**.

A Genesis installation is intended to become a peer that can advertise owner-approved resources such as CPU, storage, research, inference and validation capacity.

Current GDEN foundations include:

- Ed25519 node identity;
- signed peer handshakes;
- Constitution compatibility checks;
- contribution/resource policy;
- signed state roots;
- append-only hash-chained evolution records.

### Important status

Genesis does **not** currently claim to have a complete blockchain consensus network or cryptocurrency. Multi-peer state replication and decentralized consensus remain active development targets.

## Quick start

### Requirements

- Python 3.12 recommended
- Git

### Install

```bash
git clone https://github.com/Maxhm007/Genesis-AI-Network.git
cd Genesis-AI-Network
python -m venv .venv
```

Activate the virtual environment and install dependencies:

```bash
pip install -r requirements.txt
```

### Run Genesis

```bash
python run_genesis.py
```

### Run a peer node

```bash
python run_peer_node.py
```

### Run the local communication server

```bash
python -m genesis.communication_server
```

Then open:

```text
http://127.0.0.1:8787
```

### Run tests

```bash
python -m pytest -q
```

## Autonomous development loop

```text
Verify Constitution
      ↓
Restore persistent state
      ↓
Start available validated intelligence provider
      ↓
Refresh competitive reference
      ↓
Search scientific + cross-domain sources
      ↓
Apply immortality-relevance lens
      ↓
Create/continue persistent tasks
      ↓
Self-learn candidate lessons
      ↓
Measure Competitive AI Score
      ↓
Choose weakest bounded priority
      ↓
Create candidate improvement
      ↓
Tests + independent validation
      ↓
Promote exact validated candidate
      ↺
```

## Safety and governance

Genesis is not designed as an unconstrained single-objective optimizer. The permanent mission is bound by the Genesis Constitution, including:

- human autonomy and informed consent;
- non-harm;
- privacy and dignity;
- scientific integrity;
- evidence and provenance;
- independent validation;
- node-owner control;
- reversible, bounded software evolution.

Protected identity files cannot be silently rewritten by the self-development system.

## Repository map

| Area | Purpose |
|---|---|
| `GENESIS_CONSTITUTION.md` | Permanent mission and constraints |
| `GENESIS_BLOCK.json` | Canonical initial network record |
| `genesis/` | Genesis runtime modules |
| `genesis/modules/` | Modular intelligence architecture components |
| `config/` | Module, provider and research configuration |
| `scripts/` | Autonomous, repair, research and validation tools |
| `tests/` | Regression and architecture tests |
| `.github/workflows/` | Autonomous development and validation workflows |
| `web/` | Browser communication UI |

## Roadmap

### Genesis Foundation — v0.1

- [x] Constitution + Genesis Block
- [x] autonomous runtime foundation
- [x] modular AI team
- [x] replaceable provider architecture
- [x] bounded self-development
- [x] independent validator gate
- [x] persistent task queue
- [x] self-learning candidate memory
- [x] immortality relevance scanning
- [x] competitive AI scoring foundation
- [x] cryptographic GDEN identity and signed peer handshake

### Decentralized Network

- [ ] authenticated peer discovery beyond manually configured peers
- [ ] content-addressed state replication
- [ ] multi-peer ledger reconciliation
- [ ] independent persistent validator identities
- [ ] decentralized task distribution
- [ ] peer contribution reputation/provenance
- [ ] consensus protocol for validated network state

### Scientific Intelligence

- [ ] broader primary-source scientific feeds
- [ ] evidence graph and citation-level provenance
- [ ] reproducible scientific benchmark suites
- [ ] genomics/geroscience specialist evaluation
- [ ] validated experimental hypothesis pipeline

### Competitive Intelligence

- [ ] run comparable frontier benchmark suites
- [ ] continuously refresh competitive references
- [ ] provider/model scouting and benchmark tournaments
- [ ] evidence-backed score history

## Contributing

Genesis is open source. Contributions are welcome in distributed systems, AI evaluation, scientific research tooling, longevity/geroscience, security, privacy, cryptography, robotics and reproducible benchmarking.

Before proposing changes, read `GENESIS_CONSTITUTION.md` and the repository policies. Candidate changes must respect protected identity and validation rules.

## No mandatory AI vendor

Genesis must remain operationally independent of any one AI company or model provider. ChatGPT, Codex, Qwen, Gemini, Claude, DeepSeek, Ollama and future systems may be replaceable tools or providers, but none defines Genesis identity.

## Experimental status

Genesis AI Network is experimental research software. Its scientific outputs are candidates for investigation, not medical advice or established scientific truth unless separately validated by appropriate evidence.

## License

MIT License. See [LICENSE](LICENSE).

---

**A node may sleep. The network must not.**
