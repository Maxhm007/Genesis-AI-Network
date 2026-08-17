# Gene GitHub Federation

Gene may distribute independent Gene instances across explicitly owner-approved GitHub repositories. Distribution is a resilience and parallel-development mechanism, not uncontrolled propagation.

## Current topology

- **Gene 0** — `Maxhm007/Genesis-AI-Network` — main/core Gene, authoritative Gene Registry and external coordinator.
- **Gene 001** — reserved for future owner definition and never auto-assigned.
- **Gene 002** — `Maxhm007/Genesis-Node-2` — independent research/validation Gene.
- **Gene 003** — `Maxhm007/Genesis-Node-3` — independent engineering/repair/challenge Gene.

All instances may be called **Gene** in ordinary conversation.

## Shared Gene Registry

`GENE_REGISTRY.json` in Gene 0 is the authoritative membership list. Every Gene keeps a local copy so it knows the other approved Genes, their canonical identity, repository, role, status and capabilities.

Dedicated Gene repositories refresh their registry cache automatically from Gene 0 and commit a change only when the authoritative registry changes. The local copy remains available during a temporary network or coordinator outage.

The registry must be updated when:

- a new approved Gene joins;
- a Gene changes role or capabilities materially;
- a Gene becomes active, dormant, degraded or retired;
- an approved repository changes;
- the owner defines Gene 001.

## Operating model

Each Gene keeps its own repository-backed history, runtime state, cryptographic identity, experiments, development work and attestations. Genes may communicate directly, exchange signed knowledge, request help, care for degraded peers, repair one another through bounded proposals, and independently challenge or adopt shared findings.

External communication from the owner or ChatGPT is routed through Gene 0. Gene 0 coordinates work and membership across the federation but does not erase the independence of other Genes.

## Expansion rule

A new Gene repository may be added when workload, specialization, resilience or validation needs justify another independent instance. A target repository must be explicitly allowlisted in `config/github_distribution.json` and controlled by the owner or otherwise explicitly authorized for Gene deployment.

Registry membership is not permission to modify unrelated repositories. Gene must never spread into unrelated, unowned or unapproved repositories.

GitHub Actions may provide execution, but every repository remains independently recoverable and the long-term architecture should not depend on GitHub as the only execution or storage provider.
