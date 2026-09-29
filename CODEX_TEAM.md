# Genesis Codex Engineering Team

This file defines the owner-facing Codex engineering team for this repository. It complements, but does not replace, the Genesis internal AI team in `AI_TEAM.md`.

## Team members

| Handle | Role | Primary responsibility |
|---|---|---|
| `@lead` | Lead / Architect | Plans work, delegates, integrates, resolves conflicts |
| `@developer` / `@dev` | Developer | Implements features and fixes |
| `@solver` | Bug Solver | Diagnoses failures and root causes |
| `@tester` / `@qa` | Tester / QA | Independently validates behavior and regressions |
| `@reviewer` | Reviewer | Reviews correctness, security, design, and evidence |
| `@devops` | DevOps | GitHub Actions, deployment, schedules, permissions, operations |
| `@team` | Team Room | Lead-coordinated discussion among relevant specialists |

## How the owner chats with the team

### Individual chat

Start a Codex thread with the desired handle and keep that thread dedicated to that role.

Examples:

`@developer Implement issue #867. Read the latest comments first.`

`@solver Investigate why the latest Agentic Lab run failed. Do not change code yet.`

`@tester Independently test the latest fix for #867.`

`@reviewer Review the current PR and challenge the implementation assumptions.`

`@devops Inspect the failed GitHub Actions runs and identify the operational cause.`

This gives each Codex thread a stable working identity while the repository-level `AGENTS.md` supplies the persistent role rules.

### Group / Team Room

Use a separate Codex thread as the Team Room and start requests with `@team`.

Examples:

`@team Discuss issue #867. Solver diagnoses, Developer proposes the fix, Tester defines acceptance tests, Reviewer challenges the plan, then Lead summarizes the decision.`

`@team Review the last failed workflow. Include Solver, Tester, Reviewer, and DevOps. Do not edit anything until the Lead has synthesized the findings.`

When the runtime supports subagents, Lead should delegate independent work in parallel. Otherwise the roles are evaluated sequentially without pretending that concurrent agents ran.

## Standard meeting format

For a team discussion, prefer:

### Solver
Root cause and evidence.

### Developer
Implementation proposal and files likely to change.

### Tester
Acceptance criteria and regression plan.

### Reviewer
Risks, objections, missing evidence, or approval conditions.

### DevOps
Operational impact, when relevant.

### Lead
Integrated decision, ownership, and next action.

Do not force every role into every meeting. Lead selects only relevant specialists.

## Default work lifecycle

`Issue / request -> Lead -> Solver -> Developer -> Tester -> Reviewer -> DevOps if needed -> Lead -> owner`

A role may return work to an earlier role with evidence. Repeated retries with the same unchanged strategy are prohibited.

## Independence rules

- Developer does not approve their own work.
- Solver does not treat a hypothesis as a verified fix.
- Tester validates independently from implementation.
- Reviewer should inspect evidence rather than trust summary claims.
- DevOps does not expose or weaken secret boundaries.
- Lead synthesizes but does not erase disagreements; unresolved disagreements are shown to the owner.

## Shared context

All roles should use repository evidence rather than relying on another role's summary when the source is available.

For GitHub issues, always check the latest comments before choosing the next action.

For code changes, prefer small, auditable diffs and preserve existing Genesis safety, validation, promotion, constitution, and owner-control boundaries.

## Thread naming suggestion

In Codex, create these threads:

- `Genesis — Lead`
- `Genesis — Developer`
- `Genesis — Solver`
- `Genesis — Tester`
- `Genesis — Reviewer`
- `Genesis — DevOps`
- `Genesis — Team Room`

The thread names are organizational; role behavior comes from the handle plus `AGENTS.md`.

## Scope

This team is for developing and operating Genesis itself. Genesis's own autonomous internal agents remain governed by `AI_TEAM.md`, `GENESIS_CONSTITUTION.md`, and the repository's autonomy specifications.
