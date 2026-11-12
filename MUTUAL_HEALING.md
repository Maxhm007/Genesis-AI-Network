# Genesis × Eve mutual healing

**Primary purpose:** Genesis monitors, retries, and diagnoses **Eve's** failing workflows; Eve does the same for **Genesis**. They are independent recovery partners, **not chat partners**. Lighthouse is not involved.

## What is automated in v1

1. Each watchdog checks the other GitHub repository's recent failed workflow runs (48-hour window).
2. If a run has **failed once**, it requests GitHub's native **rerun failed jobs** action (at most one recovery operation per watchdog execution).
3. If the same run remains failed on a second attempt, it prepares a **deduplicated repair issue** in the *affected* repository, with exact failed job and step names and the run URL. It does not guess the cause.
4. Subsequent checks skip already reported runs and move to the next actionable failure.
5. Existing repair scripts and CI continue to be responsible for code changes; this watchdog **does not** yet generate or deploy patches.

This handles transient infrastructure faults automatically. Persistent software defects require a tested code patch. Creating a repair issue is an escalation, **not proof of healing**.

## Schedule (Asia/Dhaka)

- **Genesis → Eve:** daily at 07:00 and 19:00
- **Eve → Genesis:** daily at 07:15 and 19:15

Schedules are installed but **paused until explicitly enabled** using a repository variable, to conserve GitHub Actions minutes and prevent unauthenticated operation.

## One-time configuration

Each repository needs only **one fine-grained token scoped to the OTHER repository**.

**In Genesis repository:**
- Settings → Secrets and variables → Actions → new repository secret `PEER_HEAL_TOKEN`: token with access only to `Maxhm007/Eve`, **Actions: Read and write**, **Issues: Read and write**, and repository metadata read.
- Settings → Secrets and variables → Actions → Variables → `MUTUAL_HEAL_ENABLED=true`.

**In Eve repository:**
- `PEER_HEAL_TOKEN`: separate token restricted only to `Maxhm007/Genesis-AI-Network`, with the same Actions and Issues rights.
- `MUTUAL_HEAL_ENABLED=true`.

Never share tokens in chat, issues, commits, or workflow logs. Do not reuse the token for software execution or broader repo administration. Prefer a GitHub App installation with short-lived tokens when feasible. Permissions for GitHub Actions retry APIs are distinct from Contents write; the watchdog intentionally has no code-edit or merge permission.

No language model, API bill, GPU, chat exchange, shared signing key, or Lighthouse runtime is required for this first recovery stage.

## Verification

- Unit tests: `python -m unittest discover -s tests -p test_mutual_healer.py -v`.
- Enable the variables and secrets, then use Actions → **Genesis heals Eve** or **Eve heals Genesis** → Run workflow.
- A successful run may report `healthy_or_no_recent_failed_runs` without changing anything.
- On a real recent failure, verify one native rerun request, followed (if it fails twice) by a `[Mutual Heal]` repair issue in the affected repository.
- Verify jobs are not retried indefinitely. The watchdog avoids runs older than 48 hours, ignores the previous research-chat workflows, and takes at most one recovery action per execution.
- To stop autonomous recovery immediately, set `MUTUAL_HEAL_ENABLED=false` in either repository or disable the respective workflow in GitHub Actions.

## Protection and limitations

- GitHub's scoped token only accesses the *peer repository*, not the agent's own repo.
- No untrusted code is executed, no remote commands are run, no auto-merge, and no workflow is silently re-enabled.
- Does **not** prove a workflow was fixed until a subsequent run is successful.
- Failing jobs on GitHub Actions do not always indicate a code defect; retrying is appropriate only once.
- If the peer repository is unreachable, the watchdog reports an error; it does not claim recovery.
- The workflow run list is bounded to 30 recent failures; issue lookup uses GitHub search and requires complete search results.
- **Next engineering milestone:** have Genesis/Eve create minimal patches in isolated worktrees, reproduce the failure, run independent tests, and open verified repair PRs. This must keep generated code and peer content away from credentials, and retain human review before merging.

The legacy autonomous research-conversation workflows have been removed. Previous `peer_autonomy.py` scripts remain as historical source, but **are not scheduled or part of the healing process**.
