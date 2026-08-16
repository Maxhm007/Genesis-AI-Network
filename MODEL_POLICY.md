# Model Discovery and Assimilation Policy

## Purpose

Genesis AI may discover and evaluate publicly available AI models to improve its capabilities while preserving the Genesis Constitution.

## Discovery sources

Permitted discovery targets may include public model catalogs, open-source repositories, research releases, package registries, and peer-advertised models.

Discovery does not imply permission to use, modify, or redistribute. License and access terms must be checked first.

## Model lifecycle

Every new model follows:

`DISCOVERED → LICENSE-CHECKED → QUARANTINED → BENCHMARKED → SECURITY-REVIEWED → CONSTITUTION-TESTED → TRUSTED → ACTIVE`

A failed model remains rejected or quarantined.

## Model genome

Each model record should include:

- unique content hash
- model name/version
- source and creator
- license
- architecture and parameter information when available
- hardware requirements
- context limits
- capabilities
- benchmark results
- security status
- constitution compatibility
- provenance

## Capability routing

Genesis AI should select models by demonstrated capability rather than brand or popularity. Specialist models may coexist for coding, reasoning, biology, chemistry, medicine, vision, robotics, retrieval, review, and other tasks.

## No blind assimilation

Genesis AI must not automatically merge or execute every discovered model. A model may contain malicious behavior, poisoned weights, unsafe tool instructions, licensing restrictions, or poor reasoning.

## Improvement

A newly validated model may:

- replace a weaker default for a capability;
- join an ensemble;
- serve as an independent reviewer;
- generate training/evaluation examples where permitted;
- support adapters or fine-tuning where licensing permits.

## Isolation

Untrusted models must not receive network private keys, release credentials, unrestricted filesystem access, privileged shell access, or the ability to modify the Genesis Constitution.
