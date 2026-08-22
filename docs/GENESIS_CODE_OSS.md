# Genesis DevLab Code - OSS

## Purpose

Code - OSS is the IDE/workspace capability used by Genesis DevLab for self-repair and self-development work. DevLab remains the engineering authority that decides the bounded task, allowed target paths, tests, retry behavior, and candidate handoff.

Code - OSS is a tool. It is not a promotion or validation authority.

## Repository layout

```text
Genesis-AI-Network/
├── genesis/
│   └── devlab/
│       ├── module.py
│       ├── workspace.py
│       └── code_oss.py
├── vendor/
│   └── code-oss/        # Git submodule: microsoft/vscode
└── runtime/
    └── task_reviews/
        └── devlab/
            └── code_oss/
                └── <session>/workspace/
```

The upstream Code - OSS source is kept out of the Genesis Python package because it has its own large Node/Electron build system.

## Safety boundary

Genesis must never open the canonical repository as a writable Code - OSS self-repair workspace.

For each task:

1. DevLab authorizes one or more source paths.
2. `CodeOSSBridge.create_session()` copies the repository to an isolated runtime workspace.
3. Code - OSS opens only that isolated copy.
4. Genesis may inspect, edit, search, debug, and run bounded tests there.
5. `candidate_proposal()` imports only an explicitly authorized changed path.
6. `submit_candidate()` hands that exact edit to the existing `SelfDevelopmentExecutor`.
7. Existing security checks, independent validators, signed quorum, and promotion rules remain authoritative.

The session manifest explicitly records:

- `direct_main_write = false`
- `validation_authority = false`
- `protected_file_bypass = false`
- `candidate_import_only = true`

Editing extra files inside the isolated IDE session does not grant permission to import or promote those files.

## Initialization

After cloning or pulling Genesis:

```bash
git submodule update --init --recursive
```

The submodule is pinned to a specific Code - OSS commit by the Genesis repository. Updating it is therefore an auditable Genesis change.

The default development launcher is:

- Linux/macOS: `vendor/code-oss/scripts/code.sh`
- Windows: `vendor/code-oss/scripts/code.bat`

A different launcher can be supplied with `GENESIS_CODE_OSS_COMMAND`.

Code - OSS still needs its normal upstream development dependencies/build bootstrap before the launcher can run successfully on a new machine.

## Autonomous self-repair flow

```text
Genesis discovers or receives an issue
        ↓
DevLab defines bounded target + acceptance
        ↓
CodeOSSBridge creates isolated workspace
        ↓
Genesis works in Code - OSS
        ↓
DevLab runs tests in isolated workspace
        ↓
Genesis revises until candidate is ready
        ↓
DevLab imports exact authorized candidate
        ↓
SelfDevelopmentExecutor
        ↓
Security + Validator A + Validator B
        ↓
Signed quorum
        ↓
Promotion to main
```

## Future Genesis Code fork

The first integration pins the official `microsoft/vscode` upstream directly. When a dedicated `Maxhm007/Genesis-Code` fork/repository is available, change the submodule URL to that repository and keep the same DevLab bridge boundary.

Genesis-specific UI should then live in the fork as an extension/workbench integration, while `genesis.devlab.code_oss` remains the stable control interface.
