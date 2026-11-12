# Mutual Healing Phase 2 — Tested Repair PR

This phase keeps **Genesis healing Eve** and **Eve healing Genesis**, without conversation workflows. It adds a separate, independently gated code-repair path to the existing failure-retry watchdog.

## Pipeline

1. **Propose (unprivileged)**: Read a genuine second-attempt failed `main` CI run in the OTHER repository from the past 48 hours. Retrieve failed-test evidence and a Python source file referenced by the traceback. Ask the healer's independently configured reasoning model for ONE narrow unified-diff patch. The model must return `NO_SAFE_PATCH` when evidence is insufficient.
2. **Validate (no secrets)**: Clone the exact failed SHA of the OTHER repository. Execute Python unittest before and after applying the patch. Require baseline **failure** and patched **pass**. Reject changes to tests, workflow files, setup files, binary files, renames, symlinks, multiple files, broad patches or file changes outside the declared path.
3. **Publish (peer-scoped GitHub token only)**: Read the already-validated patched file and test attestation, never execute candidate code in this credential-bearing job. Create a unique `mutual-heal/<healer>-run-<run_id>` branch on the OTHER repository, commit the single changed file and open a pull request requiring review. No auto-merge or deployment.

The existing v1 watchdog still retries one transient failure and creates evidence-backed issues for failures persisting after retry. Phase 2 can run separately on a daily schedule once configured.

## Activation

For **Genesis** repository (which repairs Eve):
- Actions variable `MUTUAL_HEAL_REPAIR_ENABLED=true`
- Actions variables `REPAIR_MODEL_ENDPOINT` (HTTPS OpenAI-compatible URL ending `/v1/chat/completions`) and `REPAIR_MODEL_NAME`
- Secret `REPAIR_MODEL_API_KEY` if the model provider requires it
- Optional secret `REPAIR_READ_TOKEN` with read-only Actions/Contents access to Eve for detailed logs
- Secret `REPAIR_PR_TOKEN` with access **only to Eve**, Contents write and Pull requests write (plus basic metadata read)

For **Eve** repository (which repairs Genesis), configure the analogous variables and distinct tokens scoped **only to Genesis**.

**Never share keys in chat, issues or commits.** A token that can write PR content is supplied ONLY to the final publish job. It is not supplied to the model-proposal or code-test job.

Schedules are gated on the opt-in variable and model settings. If disabled, they skip without starting runners. A GitHub-hosted runner cannot reach a model hosted on your own computer at localhost; use a reachable provider or run the pipeline locally with separated privilege boundaries.

## Security and scope

- Candidate patches are treated as hostile. All target tests run on an isolated short-lived runner without repository write secrets.
- A passing patched test alone does **not** prove that code is safe, correct in production, or fixes every failure. The pull request requires independent code review and follow-up CI checks.
- This v2 supports only strictly restricted changes to 1–4 existing literal values in Python `return` statements. Arbitrary imports, calls, control-flow edits, test rewrites and module/fixture repairs are **not eligible for automatic verified publication**, even if their tests appear to pass. This protects against generated code forging its own unittest completion evidence. Broader repairs require manual/independently trusted validation and review. The test command remains `python -m unittest discover -s tests -v`. Other languages, installation failures, missing evidence, unreproducible failures and larger refactors are intentionally rejected rather than guessed.
- This system is resource-bounded: one target failed run, one model request, one patch, one baseline test and one patched test per cycle; jobs have fixed timeouts.
- If GitHub cannot retrieve a useful log and pinned source file, no speculative patch is generated.
- Never automatically enable workflows, bypass protected branches, alter credential permissions, close issues, or merge PRs.
- One review branch per run prevents repeated PR creation when the same failure is encountered again. If the branch exists, the publisher fails closed rather than overwriting it.
- The first successful model-authored cross-repository repair is **not yet verified**. This is a tested pipeline implementation, not a claim that each AI has repaired its peer.

## Links

- Genesis → Eve: [GitHub Actions workflow](https://github.com/Maxhm007/Genesis-AI-Network/actions/workflows/repair-eve-v2.yml)
- Eve → Genesis: [GitHub Actions workflow](https://github.com/Maxhm007/Eve/actions/workflows/repair-genesis-v2.yml)
- [Mutual healing issue #1174](https://github.com/Maxhm007/Genesis-AI-Network/issues/1174)

## Test completion hardening

A trusted wrapper emits an explicit completed-suite record after the unittest runner returns, and requires nonempty discovered/executed tests, consistent status and a nondecreasing test count. A zero exit before suite completion is rejected. This in-process record cannot by itself authenticate arbitrary executable Python, so **both** the zero-secret validation job **and** token-bearing publication job enforce the same strict AST policy: only literal return values can change. A potentially more complex model patch is rejected, not mislabeled as verified. This is intentionally narrower than general-purpose autonomous code healing.
