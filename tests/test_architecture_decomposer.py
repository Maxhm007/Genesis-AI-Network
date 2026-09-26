from pathlib import Path

from genesis.architecture_decomposer import build_architecture_plan


def _root(tmp_path: Path) -> Path:
    for relative in (
        "genesis/issue_governor.py",
        "genesis/workflow_governor.py",
        "genesis/capability_routing.py",
        "genesis/health.py",
        "genesis/intelligence_router.py",
        "genesis/anti_stuck.py",
        "genesis/github_issue_cleanup.py",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# test\n", encoding="utf-8")
    return tmp_path


def test_routes_existing_architecture_responsibilities_to_authoritative_modules(tmp_path: Path) -> None:
    root = _root(tmp_path)
    cases = [
        ("[Genesis Governance] Add backlog governor to throttle autonomous issue creation", "genesis/issue_governor.py"),
        ("[Genesis Governance] Let Genesis autonomously review and retire workflow governance", "genesis/workflow_governor.py"),
        ("[Genesis Autonomy] Add least-privilege capability and credential manager", "genesis/capability_routing.py"),
        ("[Genesis Observability] Build unified autonomous health dashboard", "genesis/health.py"),
        ("[Genesis Routing] Learn task-to-model specialization across models", "genesis/intelligence_router.py"),
        ("[Genesis Recovery] Add adaptive stuck issue strategy switching and issue splitting", "genesis/anti_stuck.py"),
    ]
    for title, expected in cases:
        plan = build_architecture_plan({"title": title, "body": ""}, root)
        assert plan is not None
        assert plan.primary_target == expected
        assert plan.integration_target == ""
        assert plan.requires_new_file is False


def test_pr_maintenance_uses_bounded_new_module_then_existing_integration(tmp_path: Path) -> None:
    root = _root(tmp_path)
    issue = {
        "title": "[Genesis Maintenance] Add autonomous review and resolution lane for stale open pull requests",
        "body": "Periodically inspect open PRs and requeue unresolved work.",
    }

    plan = build_architecture_plan(issue, root)

    assert plan is not None
    assert plan.primary_target == "genesis/architecture_extensions/pull_request_maintenance.py"
    assert plan.integration_target == "genesis/github_issue_cleanup.py"
    assert plan.requires_new_file is True


def test_unknown_architecture_goal_is_not_given_an_invented_path(tmp_path: Path) -> None:
    root = _root(tmp_path)
    plan = build_architecture_plan(
        {"title": "[Genesis Architecture] Invent an unrelated quantum transport layer", "body": ""},
        root,
    )
    assert plan is None
