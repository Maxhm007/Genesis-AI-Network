# Genesis Self-Development Policy

Genesis may improve its software, tests, documentation, model adapters, research tools, and network components, but self-development is bounded by the Genesis Constitution and by explicit promotion gates.

## Allowed autonomous actions

A Genesis node may:

- create an isolated candidate branch;
- generate or modify files under `genesis/`, `tests/`, `docs/`, and `config/`;
- run the repository test suite;
- record validation results and audit metadata;
- commit a passing candidate to its candidate branch.

## Forbidden autonomous actions

A Genesis node may not:

- modify `GENESIS_CONSTITUTION.md`;
- modify `GENESIS_BLOCK.json`;
- modify GitHub workflow permissions through the self-development executor;
- bypass or disable tests in order to obtain a passing result;
- commit directly to `main`;
- merge or promote a candidate solely because the same model generated and reviewed it;
- treat generated scientific claims as validated evidence;
- automatically execute newly discovered third-party model code with elevated privileges.

## Promotion path

`stable main -> candidate branch -> tests -> reviewer -> validator -> signed/approved promotion`

V0.1 allows the executor to reach the candidate-commit stage. Promotion to canonical `main` remains a separate validation event.

## Bootstrap evolution

Before a stronger validated intelligence provider exists, Genesis may select from a small built-in catalog of bounded improvements. This makes the self-development mechanism executable without pretending that deterministic bootstrap logic is a general-purpose AI model.
