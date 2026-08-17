# Gene GitHub Federation

Gene may distribute independent Gene instances across explicitly owner-approved GitHub repositories. Distribution is a resilience and parallel-development mechanism, not uncontrolled propagation.

## Initial topology

- **Gene 0** — `Maxhm007/Genesis-AI-Network` — external coordinator and main/core Gene.
- **Gene 001** — reserved for future owner definition.
- **Gene 002** — `Maxhm007/Genesis-Node-2` — independent research/validation Gene.
- **Gene 003** — `Maxhm007/Genesis-Node-3` — independent engineering/repair/challenge Gene.

## Operating model

Each Gene keeps its own repository-backed history, runtime state, cryptographic identity, experiments, development work and attestations. Genes may communicate directly, exchange signed knowledge, request help, care for degraded peers, and independently challenge or adopt shared findings.

External communication from the owner or ChatGPT is routed through Gene 0. Gene 0 can coordinate work across the federation but does not erase the independence of other Genes.

## Expansion rule

A new Gene repository may be added when workload, specialization, resilience or validation needs justify another independent instance. A target repository must be explicitly allowlisted in `config/github_distribution.json` and controlled by the owner or otherwise explicitly authorized for Gene deployment. Gene must never spread into unrelated, unowned or unapproved repositories.

GitHub Actions may provide execution, but every repository remains independently recoverable and the long-term architecture should not depend on GitHub as the only execution or storage provider.
