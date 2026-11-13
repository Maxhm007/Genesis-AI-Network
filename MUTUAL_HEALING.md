# Genesis × Eve: token-free local recovery (Stage 1)

This stage replaces the need to install **personal access tokens** for autonomous
GitHub Actions recovery. Both repositories run their own watchdog with GitHub's
automatically minted short-lived `GITHUB_TOKEN`:

- **Genesis** retries its own failed jobs once, then opens a deduplicated evidence
  issue for persistent failures in **Genesis**.
- **Eve** performs the same recovery in **Eve**.
- Each workflow uses only `actions: write`, `issues: write`, `contents: read`.
- Both fail closed for attempts to use their local token against a peer repository.
- Both run twice daily (Genesis 07:00 and 19:00; Eve 07:15 and 19:15, Dhaka).
- Each watchdog excludes itself to avoid a retry loop, and checks no more than
  thirty failed runs from the last 48 hours. **No AI code is auto-merged.**
- Use Actions → `self-heal.yml` → Run workflow to test. Inspect real logs:
  `healthy_or_no_recent_failed_runs` means no recent work, NOT a healed bug.

### Crucial limitation

GitHub's `GITHUB_TOKEN` is repository-scoped. It **cannot rerun a peer's
workflows or open issues/PRs in the peer repository**. Earlier proposals
describing direct cross-repository writes without credentials are not possible.

The previous peer-write workflows `heal-eve.yml` / `heal-genesis.yml` and
`repair-*-v2.yml` remain **opt-in gated**. They must not be enabled with
`MUTUAL_HEAL_ENABLED` or `MUTUAL_HEAL_REPAIR_ENABLED` unless the requisite
separately scoped credentials are intentionally configured.

### Next stage: reciprocal advice, without trusting peer code

A second stage can publish **non-executable repair advice and verified public
evidence** in each source repository. The recipient should only read that data,
reproduce the failure independently, and create local reviewed proposals using
its **own** ephemeral token. Public GitHub issue/Actions data is untrusted.
Never execute peer-provided commands, import arbitrary peer code, or accept
peer-provided attestation as proof. A cross-repository AI code repair is **not
yet verified** by this stage.

### Tests

`python -m unittest discover -s tests -p test_mutual_healer.py -v`

### Controls

To suspend a repository's watchdog, disable `self-heal.yml` in its Actions
page. No token setup and no custom Actions variable is necessary for this
workflow. Existing `PEER_HEAL_TOKEN` and `MUTUAL_HEAL_ENABLED` are **not read**
by `self-heal.yml`.
