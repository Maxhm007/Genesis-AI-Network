# Genesis AI Team

Genesis uses a role-based AI team rather than one permanent model.

## Core roles

1. **Planner** — turns the permanent mission into bounded, testable work plans.
2. **Researcher** — searches scientific evidence and records provenance and uncertainty.
3. **Model Scout** — evaluates public models, licenses, capabilities, hardware needs, and risk.
4. **Engineer** — proposes isolated software improvements; never overwrites stable code directly.
5. **Scientist** — develops testable longevity hypotheses and separates evidence from speculation.
6. **Reviewer** — challenges assumptions, evidence quality, security, and hidden dependencies.
7. **Validator** — independently checks whether a candidate is eligible for promotion.
8. **Network Steward** — improves multi-node resilience, interoperability, replication, and graceful degradation.

## Independence rule

The team is part of Genesis architecture, but no particular provider or model is part of Genesis identity. Roles may be routed across any compatible intelligence providers. If none are available, Genesis remains alive in maintenance mode and records pending team work rather than fabricating results.

## Trust rule

Agent output is always candidate knowledge until independently validated. An engineer agent cannot approve its own code. A researcher cannot promote its own scientific claim. A model scout cannot grant a newly discovered model privileged execution.

## Current V0.1 workflow

`research/model discovery → specialist agents → reviewer → validator → candidate record`

Actual source-code promotion remains gated by testing and the release/validation process defined elsewhere in the repository.
