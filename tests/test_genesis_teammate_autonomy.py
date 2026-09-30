from pathlib import Path

import pytest

from scripts import genesis_teammate
from scripts.genesis_teammate import classify


ROOT = Path(__file__).resolve().parents[1]


def test_autonomous_issue_objective_routes_to_recovery_for_stuck_work():
    assert classify("Autonomous Genesis development task: workflow is stuck and retry failed") == "recovery"


def test_autonomous_issue_objective_routes_to_sentinel_for_validation():
    assert classify("Autonomous Genesis development task: validate test regression") == "sentinel"


def test_autonomous_issue_objective_routes_to_atlas_for_architecture():
    assert classify("Autonomous Genesis development task: redesign architecture") == "atlas"


def test_autonomous_issue_objective_defaults_to_forge():
    assert classify("Autonomous Genesis development task: implement bounded fix") == "forge"


def _issue(*, labels=("genesis-autonomous",), **overrides):
    issue = {
        "number": 867,
        "title": "Bounded Genesis task",
        "body": "Implement and validate a bounded change.",
        "state": "open",
        "labels": [{"name": label} for label in labels],
    }
    issue.update(overrides)
    return issue


@pytest.mark.parametrize(
    "issue",
    [
        _issue(labels=()),
        _issue(labels=("genesis-autonomous", "genesis-waiting-capability")),
        _issue(labels=("agentic-lab", "genesis-needs-human")),
        _issue(body="<!-- genesis-team-task -->"),
        _issue(title="[Nexus Task] Generated internal work"),
        _issue(state="closed"),
        _issue(pull_request={"url": "https://api.github.com/pulls/1"}),
    ],
)
def test_autonomous_intake_excludes_non_actionable_or_gated_issues(issue):
    assert not genesis_teammate.is_autonomous_issue(issue)


def test_autonomous_intake_accepts_open_genesis_work():
    assert genesis_teammate.is_autonomous_issue(_issue(labels=("agentic-lab",)))


def test_open_development_issues_only_returns_intake_eligible_work(monkeypatch):
    eligible = _issue(number=900)
    gated = _issue(number=901, labels=("genesis-autonomous", "genesis-waiting-capability"))
    internal = _issue(number=902, body="<!-- genesis-team-task -->")
    workspace = _issue(number=1000)
    monkeypatch.setattr(
        genesis_teammate,
        "paged_get",
        lambda _path: [eligible, gated, internal, workspace],
    )

    assert genesis_teammate.open_development_issues() == [eligible]


def test_autonomous_assignment_passes_authoritative_source_issue(monkeypatch):
    selected = _issue(number=912, title="Add a bounded capability")
    monkeypatch.setattr(genesis_teammate, "open_development_issues", lambda: [selected])
    monkeypatch.setattr(genesis_teammate, "autonomous_claim_exists", lambda _number: False)
    comments = []
    dispatches = []
    monkeypatch.setattr(genesis_teammate, "comment", lambda number, body: comments.append((number, body)))
    monkeypatch.setattr(
        genesis_teammate,
        "dispatch",
        lambda workflow, inputs: dispatches.append((workflow, inputs)),
    )

    genesis_teammate.autonomous_development("run-1")

    assert len(dispatches) == 1
    assert dispatches[0][1]["source_issue"] == "912"
    assert dispatches[0][1]["source_comment_id"] == "autonomous-912-run-1"


def test_autonomous_agent_reports_on_source_without_creating_duplicate_issue(monkeypatch):
    comments = []
    monkeypatch.setattr(genesis_teammate, "request", lambda *_args, **_kwargs: _issue(number=912))
    monkeypatch.setattr(genesis_teammate, "comment", lambda number, body: comments.append((number, body)))
    monkeypatch.setattr(genesis_teammate, "provider_reason", lambda *_args: ("test-provider", "bounded findings"))
    monkeypatch.setattr(
        genesis_teammate,
        "create_execution_issue",
        lambda *_args: pytest.fail("autonomous work must not create a duplicate issue"),
    )

    genesis_teammate.agent_run("forge", "Bounded task", "autonomous-912-run-1", 1000, 912)

    assert any(
        number == 912 and "genesis-team-source-result:autonomous-912-run-1:forge" in body
        for number, body in comments
    )


def test_autonomous_handoff_keeps_authoritative_source_issue(monkeypatch):
    comments = []
    dispatches = []
    monkeypatch.setattr(genesis_teammate, "request", lambda *_args, **_kwargs: _issue(number=912))
    monkeypatch.setattr(genesis_teammate, "comment", lambda number, body: comments.append((number, body)))
    monkeypatch.setattr(genesis_teammate, "provider_reason", lambda *_args: ("test-provider", "bounded findings"))
    monkeypatch.setattr(
        genesis_teammate,
        "dispatch",
        lambda workflow, inputs: dispatches.append((workflow, inputs)),
    )
    monkeypatch.setattr(
        genesis_teammate,
        "create_execution_issue",
        lambda *_args: pytest.fail("autonomous work must not create a duplicate issue"),
    )

    genesis_teammate.agent_run("forge", "Fix a bounded task", "autonomous-912-run-1", 1000, 912)

    assert len(dispatches) == 1
    assert dispatches[0][1]["source_issue"] == "912"
    assert dispatches[0][1]["source_comment_id"] == "autonomous-912-run-1"


def test_autonomous_agent_skips_source_that_became_lifecycle_gated(monkeypatch):
    comments = []

    def get_issue(*_args, **_kwargs):
        return _issue(number=912, labels=("genesis-autonomous", "genesis-waiting-capability"))

    monkeypatch.setattr(genesis_teammate, "request", get_issue)
    monkeypatch.setattr(genesis_teammate, "comment", lambda number, body: comments.append((number, body)))
    monkeypatch.setattr(
        genesis_teammate,
        "provider_reason",
        lambda *_args: pytest.fail("gated source must not reach a specialist"),
    )

    genesis_teammate.agent_run("forge", "Bounded task", "autonomous-912-run-1", 1000, 912)

    assert len(comments) == 2
    assert all("genesis-team-autonomous-skip:" in body for _number, body in comments)


def test_specialist_workflows_accept_source_issue_as_optional_dispatch_input():
    workflows = ROOT / ".github" / "workflows"
    for workflow_name in genesis_teammate.CONFIG["workflows"].values():
        text = (workflows / workflow_name).read_text(encoding="utf-8")
        assert "source_issue:" in text
        assert "SOURCE_ISSUE: ${{ inputs.source_issue }}" in text
        assert "--source-issue" in text
