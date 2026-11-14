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
- Each watchdog excludes itself to avoid a retry loop, ignores historical pull
  requests and non-main branches, and checks no more than thirty failed runs
  from the last 48 hours. **No AI code is auto-merged.**
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

## Stage 3: Reviewed code-repair PRs in the affected repository (no cross-repo PAT)

New workflow: `.github/workflows/local-repair-v2.yml`. The target repository
runs its own `repair_v2.py` in **local target mode**, with the opposite
agent identity. It only reads or modifies its *own* repo using GitHub's
short-lived `GITHUB_TOKEN`.

The three-stage separation remains mandatory:

1. **Prepare**: use public/local failed GitHub Actions evidence on `main`
   after at least two attempts. Ask an independently configured model for
   one narrow patch. This job has read-only permissions, no peer-write token.
2. **Verify**: clone the pinned failing baseline, reproduce test failure,
   apply a tightly constrained literal-return change, rerun all unittest tests
   with **no model credentials or write token**. Refuse incomplete tests.
3. **Review PR**: use the current repository's `GITHUB_TOKEN` to publish
   the validated file into a new branch and open a review-only PR. Never
   run untrusted candidate code in this credential-bearing step. Never
   auto-merge.

### Configuration and limits

- **No personal access token or `PEER_HEAL_TOKEN` is needed** for this
  replacement local PR path.
- GitHub Actions may require enabling **Allow GitHub Actions to create
  and approve pull requests** in repository Settings > Actions > General
  before a `GITHUB_TOKEN` can open a PR. Keep required human review,
  protected branches and CI in place; the token does not bypass them.
- Set `MUTUAL_HEAL_REPAIR_ENABLED=true`, `REPAIR_MODEL_ENDPOINT` (full
  HTTPS URL ending in `/v1/chat/completions`) and `REPAIR_MODEL_NAME`.
  If the selected model provider requires authentication, set its
  `REPAIR_MODEL_API_KEY` secret. **A model API key may still be needed**;
  eliminating cross-repo GitHub tokens does not provide free model inference.
- All three configuration variables are deliberately **opt-in**. Without a
  model, the scheduled prepare job skips instead of fabricating repairs.
- The authorized change is strictly 1–4 literal values in existing Python
  `return` statements. Arbitrary AI edits or automatic merges are not enabled.
- PRs created using `GITHUB_TOKEN` may not automatically trigger the same
  GitHub Actions event chain as human-created PRs. Independent review and
  explicit CI verification may be required.
- Legacy peer-secret workflows are **manual-only** and no longer scheduled,
  preventing duplicate obsolete PAT recovery loops.

This is operational tooling, **not proof of source healing** until a genuine
failing `main` test is reproduced, a validated PR is opened, reviewed and
its eventual follow-up CI succeeds.

### No-model automatic candidate path (bounded)

The `local-repair-v2.yml` prepare job now runs on schedule without repository
variable setup. If a model endpoint + model name are configured, the existing
model candidate generator remains available. Otherwise it tries a **small
deterministic repair hypothesis**, not a general AI solver:

- Only a completed, twice-failed test run on `main` within 48 hours qualifies.
- GitHub's failed-job logs must contain one unambiguous observed-versus-expected
  integer/boolean assertion; the pinned traceback must identify an ordinary
  Python source file with exactly one matching literal `return`.
- The generator changes only that literal, and the existing strict AST guard
  verifies that no other executable structure changed.
- A separate job without credentials must demonstrate baseline tests **fail**
  and patched tests **pass** with no additional skips or incomplete reporting.
- The publication job creates only a **review-only PR** using the target
  repo's own `GITHUB_TOKEN`. Branch rules and human review still apply.

No assert evidence, unclear source, passing baseline, model credential or
PR-creation permission: the pipeline safely declines or reports the blocker,
rather than pretending to have healed code. No secrets or cross-repo PATs
are needed for the deterministic mode. The previous opt-in model variables
are OPTIONAL for the model-powered path, not required for this limited path.
