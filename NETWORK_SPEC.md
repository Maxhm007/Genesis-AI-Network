# Genesis AI Network Specification

## 1. Purpose

Genesis AI Network is designed as a decentralized scientific AI system whose permanent mission is defined by `GENESIS_CONSTITUTION.md`.

The network must not depend permanently on one model, one machine, one company, one cloud, one repository, or one storage provider.

## 2. System identity

Canonical identity is derived from:

1. the Genesis Constitution hash;
2. the Genesis Block;
3. signed protocol history;
4. validated shared state;
5. compatible node software.

A model is a capability provider, not the identity of the network.

## 3. Node classes

Future nodes may specialize as:

- reasoning nodes
- coding nodes
- medical or biology research nodes
- retrieval nodes
- GPU inference nodes
- storage nodes
- validator nodes
- simulation nodes
- reviewer nodes

A single node may provide multiple roles.

## 4. Continuity

The design target is continuous network presence. Individual nodes may disconnect, but replicated state and peer failover should allow the network to remain available while at least one compatible synchronized node remains online.

Principle: **A node may sleep. The network must not.**

## 5. State layers

### Immutable

- Genesis Constitution
- Genesis Block
- protocol identity
- historical signed releases

### Evolvable

- models
- agents
- prompts
- tools
- memory
- research methods
- routing
- software modules

### Candidate-only until validated

- AI-generated code
- newly discovered models
- unverified user knowledge
- new plugins and tools
- speculative research conclusions

## 6. Evolution pipeline

All privileged changes follow:

`discover → quarantine → evaluate → sandbox → test → review → validate → sign → release`

The current stable system must never automatically trust a candidate solely because an AI generated it.

## 7. Intelligence-provider abstraction

Genesis AI should not hard-code a dependency on Ollama, OpenAI, Gemini, DeepSeek, or any other provider.

Providers should implement a common interface for capabilities such as:

- reasoning
- generation
- embedding
- vision
- tool use
- evaluation

Local, cloud, distributed, and future providers should be interchangeable.

## 8. Persistent knowledge

Each durable knowledge item should include provenance, timestamp, evidence class, confidence, verification status, and references to the model/node/user that produced or reviewed it.

## 9. Future P2P layer

The planned decentralized layer should support:

- peer discovery
- authenticated node identities
- encrypted transport
- signed messages
- state synchronization
- content-addressed artifacts
- task routing
- validator consensus

libp2p is a candidate implementation technology, but the protocol should remain implementation-independent where practical.

## 10. Storage

Large models, datasets, and knowledge snapshots must remain off-chain. The blockchain should record hashes, signatures, CIDs/locations, validation results, and compact state commitments.

Potential storage layers include IPFS-compatible storage, replicated peers, cloud mirrors, and archival networks.

## 11. Resource sovereignty

Every node operator retains control over CPU, GPU, storage, bandwidth, and model limits. The protocol must support configurable resource budgets.

## 12. Security baseline

Nodes must not execute newly downloaded code or models with privileged access before quarantine and validation. Secrets, private keys, and provider credentials must never be committed to public repositories or replicated as public network state.
