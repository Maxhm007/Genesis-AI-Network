# Current Task — Genesis AI V0.1

Build the smallest executable Genesis node foundation.

## Required V0.1 components

1. Constitution verifier
   - load `GENESIS_CONSTITUTION.md`
   - compute SHA-256
   - compare with `GENESIS_BLOCK.json`
   - refuse canonical startup if verification fails

2. Persistent state
   - lightweight local database
   - versioned schema
   - clear separation between trusted and candidate knowledge

3. Intelligence-provider interface
   - no mandatory Ollama dependency
   - support pluggable local/cloud/future providers

4. Model registry
   - store discovered model metadata, license status, hashes, capabilities, and trust state

5. Evolution candidate system
   - create candidate changes separately from stable code
   - run tests before promotion
   - never self-promote solely on model output

6. Audit log
   - append important events with timestamps and hashes

## Non-goals for V0.1

- cryptocurrency/token issuance
- fully autonomous privileged self-replacement
- production medical advice or interventions
- large-scale consensus
- complete P2P networking
- downloading every public model automatically

## Definition of done

A developer can clone the repository, start a Genesis node locally, verify the canonical Constitution, persist state, register intelligence providers/models, create a candidate improvement, test it, and record an auditable validation result.
