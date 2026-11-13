# Genesis × Eve: token-free local recovery (Stage 1)

This stage replaces the need to install **personal access tokens** for autonomous
GitHub Actions recovery. Both repositories run their own watchdog with GitHub's
automatically minted short-lived `GITHUB_TOKEN`:

- **Genesis** retries its own failed jobs once, then opens a deduplicated evidence
  issue for persistent failures in **Genesis**.
- **Eve** performs the same recovery in **Eve**.
- Each workflow uses only `actions: write`, `issues: write`, `contents: read`.
- Both fail closed for attempts to use their local token against a peer repository.
- Each runs **once locally and once with the other AI's immutable, vetted engine**.
  The local engine runs at 07:00/07:15 and the cross-authored engine at
  19:00/19:15 Dhaka time. Both use only the affected repository's token.
- Each watchdog excludes itself to avoid a retry loop, and checks no more than
  thirty failed runs from the last 48 hours. **No AI code is auto-merged.**
- Use Actions → `self-heal.yml` → Run workflow to test. Inspect real logs:
  `healthy_or_no_recent_failed_runs` means no recent work, NOT a healed bug.

### Reciprocal intelligence (Stage 2)

The `peer-healing-engine.yml` reusable workflow is authored and published
in each repository. Genesis calls the **immutable Eve engine** from inside
Genesis; Eve calls the **immutable Genesis engine** from inside Eve.
The GitHub Actions `workflow_call` context and short-lived `GITHUB_TOKEN`
belong to the caller. A runtime identity check rejects any attempt to use
this token to write to the other repository.

Every imported workflow is pinned to a **full commit SHA** and the imported
Python logic is itself checked out at a fixed known commit SHA. Updates to
either peer's healing algorithm therefore require reviewing and changing
the pinned hashes, rather than silently executing mutable source.

This is a genuine reciprocal *execution of healing logic*, but **not** an
unattended model-generated software patch. It can retry the affected
repository's failed jobs and open evidence tickets; it cannot modify
the peer or automatically merge code.

### Crucial limitation

GitHub's `GITHUB_TOKEN` is repository-scoped. It **cannot rerun a peer's
workflows or open issues/PRs in the peer repository**. Earlier proposals
describing direct cross-repository writes without credentials are not possible.

The previous peer-write workflows `heal-eve.yml` / `heal-genesis.yml` and
`repair-*-v2.yml` remain **opt-in gated**. They must not be enabled with
`MUTUAL_HEAL_ENABLED` or `MUTUAL_HEAL_REPAIR_ENABLED` unless the requisite
separately scoped credentials are intentionally configured.

### Next stage: reciprocal advice, without trusting peer code

A future stage can publish **non-executable repair advice and verified public
evidence** in each source repository. The recipient should only read that data,
reproduce the failure independently, and create local reviewed proposals using
its **own** ephemeral token. Public GitHub issue/Actions data is untrusted.
Never execute peer-provided commands, import arbitrary peer code, or accept
peer-provided attestation as proof. A cross-repository AI code repair is **not
yet verified** by this stage.

### Tests

`python -m unittest discover -s tests -p test_mutual_healer.py -v`

### Controls

To suspend ALL recovery in a repository, disable **both** `self-heal.yml`
and `peer-heal.yml` in its Actions page. They are independent scheduled
workflows; disabling only one does not stop the other. No token setup and no custom Actions variable is necessary for this
workflow. Existing `PEER_HEAL_TOKEN` and `MUTUAL_HEAL_ENABLED` are **not read**
by `self-heal.yml`.
