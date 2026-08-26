from __future__ import annotations

from genesis.legacy_issue_reconciler import apply_reconciliation_plan, build_reconciliation_plan


def _task_issue(number: int, *, task_type: str, source: str, target: str = "", objective: str) -> dict:
    target_line = f"- **Target:** `{target}`\n" if target else ""
    return {
        "number": number,
        "state": "open",
        "created_at": f"2026-08-26T{number % 24:02d}:00:00Z",
        "body": (
            f"<!-- genesis-task-id:task-{number} -->\n"
            f"Genesis-Problem-Fingerprint: genesis-task:task-{number}\n"
            f"- **Genesis task ID:** `task-{number}`\n"
            f"- **Task type:** `{task_type}`\n"
            f"- **Source:** `{source}`\n"
            f"{target_line}\n"
            "### Objective\n"
            f"{objective}\n\n"
            "### Acceptance\nPreserve validation and Security.\n"
        ),
    }


def test_retry_generations_collapse_but_distinct_benchmarks_do_not() -> None:
    base = "Make benchmark swe_bench_pro executable for Genesis using the official/comparable benchmark runner and pinned dataset."
    issues = [
        _task_issue(350, task_type="benchmark_runner_integration", source="genesis", objective=base),
        _task_issue(
            351,
            task_type="benchmark_runner_integration",
            source="genesis",
            objective=base + " This is integration generation 3. Do not repeat the previous implementation approach; use different repository evidence. Previous bounded attempt ended with: timed out",
        ),
        _task_issue(
            359,
            task_type="benchmark_runner_integration",
            source="genesis",
            objective="Make benchmark terminal_bench_2_1 executable for Genesis using the official/comparable benchmark runner and pinned dataset.",
        ),
    ]

    plan = build_reconciliation_plan(issues)

    assert plan["duplicate_group_count"] == 1
    assert plan["duplicate_issue_count"] == 1
    assert plan["groups"][0]["primary_issue"] == 350
    assert plan["groups"][0]["duplicate_issues"] == [351]


def test_capability_growth_failure_history_is_retry_noise() -> None:
    base = (
        "Improve the measured Genesis capability gap for benchmark swe_bench_pro (software_engineering). "
        "Validated baseline is 0.0/80.3 percent. Target exactly genesis/coding.py."
    )
    issues = [
        _task_issue(
            354,
            task_type="capability_growth",
            source="genesis.evolution_learning",
            target="genesis/coding.py",
            objective=base + " FAILURE_STRATEGY: Repeated failure pipeline_development x27: timed out",
        ),
        _task_issue(
            355,
            task_type="capability_growth",
            source="genesis.evolution_learning",
            target="genesis/coding.py",
            objective=base + " FAILURE_STRATEGY: Repeated failure pipeline_development x29: malformed output",
        ),
    ]

    plan = build_reconciliation_plan(issues)

    assert plan["duplicate_group_count"] == 1
    assert plan["groups"][0]["primary_issue"] == 354
    assert plan["groups"][0]["duplicate_issues"] == [355]


def test_manual_and_non_authoritative_issues_are_never_planned() -> None:
    authoritative = _task_issue(
        400,
        task_type="new_capability",
        source="genesis.evolution_learning",
        target="genesis/learned_capabilities.py",
        objective="Autonomously add one bounded executable Genesis capability named learned_1111111111111111. Use the learned idea: validate JSON before persistence.",
    )
    manual = {
        "number": 401,
        "state": "open",
        "body": authoritative["body"].replace("<!-- genesis-task-id:task-400 -->\n", ""),
    }
    report = {"number": 4, "state": "open", "body": "<!-- genesis-hourly-report:v2 -->"}

    plan = build_reconciliation_plan([authoritative, manual, report])

    assert plan["eligible_issue_count"] == 1
    assert plan["duplicate_group_count"] == 0


def test_distinct_target_or_source_never_merges() -> None:
    objective = "Apply one bounded source-backed capability improvement."
    issues = [
        _task_issue(1, task_type="self_upgrade", source="arxiv", target="genesis/providers.py", objective=objective),
        _task_issue(2, task_type="self_upgrade", source="github", target="genesis/providers.py", objective=objective),
        _task_issue(3, task_type="self_upgrade", source="arxiv", target="genesis/coding.py", objective=objective),
    ]

    plan = build_reconciliation_plan(issues)

    assert plan["duplicate_group_count"] == 0


def test_apply_defaults_to_dry_run_and_never_mutates() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def requester(method: str, path: str, payload: dict | None = None):
        calls.append((method, path, payload))
        return None

    plan = {
        "groups": [
            {
                "fingerprint": "genesis-objective:0123456789abcdef0123456789abcdef",
                "primary_issue": 350,
                "duplicate_issues": [351, 352],
            }
        ]
    }

    result = apply_reconciliation_plan(plan, requester=requester)

    assert result == {"mode": "dry-run", "would_close": 2, "closed": []}
    assert calls == []
