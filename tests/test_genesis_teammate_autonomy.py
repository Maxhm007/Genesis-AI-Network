import scripts.genesis_teammate as teammate
from scripts.genesis_teammate import classify


def test_autonomous_issue_objective_routes_to_recovery_for_stuck_work():
    assert classify("Autonomous Genesis development task: workflow is stuck and retry failed") == "recovery"


def test_autonomous_issue_objective_routes_to_sentinel_for_validation():
    assert classify("Autonomous Genesis development task: validate test regression") == "sentinel"


def test_autonomous_issue_objective_routes_to_atlas_for_architecture():
    assert classify("Autonomous Genesis development task: redesign architecture") == "atlas"


def test_autonomous_issue_objective_defaults_to_forge():
    assert classify("Autonomous Genesis development task: implement bounded fix") == "forge"


def test_execution_task_key_is_stable_for_source_issue_across_handoffs():
    objective = "Autonomous Genesis development task from issue #1029: Verify teammate execution"

    recovery_key = teammate.execution_task_key(objective, "autonomous-1029-run-1")
    forge_key = teammate.execution_task_key(objective, "handoff-forge-run-2")

    assert recovery_key == "source-issue-1029"
    assert forge_key == recovery_key


def test_create_execution_issue_reuses_open_source_issue_task(monkeypatch):
    objective = "Autonomous Genesis development task from issue #1029: Verify teammate execution"
    comments: list[tuple[int, str]] = []

    monkeypatch.setattr(
        teammate,
        "paged_get",
        lambda path: [
            {
                "number": 1030,
                "body": (
                    "<!-- genesis-team-task -->\n"
                    "<!-- genesis-team-task-key:source-issue-1029 -->"
                ),
            }
        ],
    )
    monkeypatch.setattr(teammate, "comment", lambda number, body: comments.append((number, body)))
    monkeypatch.setattr(
        teammate,
        "request",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not create a duplicate issue")),
    )

    number = teammate.create_execution_issue("forge", objective, "handoff-forge-run-2")

    assert number == 1030
    assert comments and comments[0][0] == 1030
    assert "genesis-team-task-reuse:handoff-forge-run-2:forge" in comments[0][1]


def test_agent_run_wakes_agentic_lab_when_execution_issue_is_reused(monkeypatch):
    objective = "Autonomous Genesis development task from issue #1029: repair failed teammate execution"
    comments: list[tuple[int, str]] = []
    wakeups: list[bool] = []

    monkeypatch.setattr(
        teammate,
        "paged_get",
        lambda path: [
            {
                "number": 1030,
                "body": (
                    "<!-- genesis-team-task -->\n"
                    "<!-- genesis-team-task-key:source-issue-1029 -->"
                ),
            }
        ],
    )
    monkeypatch.setattr(teammate, "comment", lambda number, body: comments.append((number, body)))
    monkeypatch.setattr(teammate, "provider_reason", lambda agent, task: ("test-provider", "reuse verified"))
    monkeypatch.setattr(teammate, "wake_agentic_lab", lambda: wakeups.append(True))
    monkeypatch.setattr(teammate, "dispatch", lambda workflow, inputs: None)

    teammate.agent_run("recovery", objective, "handoff-recovery-run-2", 1000)

    assert wakeups == [True]
    assert any("genesis-team-task-reuse:handoff-recovery-run-2:recovery" in body for _, body in comments)
    assert any("**Execution issue:** #1030" in body for _, body in comments)
