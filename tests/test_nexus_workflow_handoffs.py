"""Exercise Nexus dispatch failures and the actual workflow shell boundary."""
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

from scripts import genesis_teammate as team


def issue(number=867, **overrides):
    return {"number": number, "state": "open", "title": "Implement health metrics",
            "body": "Add tests, review and validate the result.",
            "labels": [{"name": "genesis-autonomous"}, {"name": "agentic-lab"}],
            **overrides}


def test_failed_nexus_dispatch_can_be_retried_then_deduplicated(monkeypatch):
    comments, dispatched = [], []
    monkeypatch.setattr(team, "issue_comments", lambda number: [
        {"body": body} for n, body in comments if n == team.CONFIG["workspaces"]["nexus"]
    ])
    monkeypatch.setattr(team, "comment", lambda n, body: comments.append((n, body)))

    def dispatch(workflow, inputs):
        dispatched.append(inputs)
        if len(dispatched) == 1:
            raise RuntimeError("GitHub dispatch unavailable")

    monkeypatch.setattr(team, "dispatch", dispatch)
    with pytest.raises(RuntimeError, match="dispatch unavailable"):
        team.nexus("Implement health metrics", "owner", "123")
    assert not team.source_already_processed("123")
    team.nexus("Implement health metrics", "owner", "123")
    assert team.source_already_processed("123")
    assert not team.source_already_processed("12")
    team.nexus("Implement health metrics", "owner", "123")
    assert len(dispatched) == 2


def test_autonomous_claim_follows_successful_dispatch_and_routes_by_title(monkeypatch):
    comments, dispatched = [], []
    monkeypatch.setattr(team, "select_autonomous_issue", lambda: issue())
    monkeypatch.setattr(team, "comment", lambda n, body: comments.append((n, body)))

    def dispatch(workflow, inputs):
        assert not any("genesis-team-autonomous-claim:" in body for _, body in comments)
        dispatched.append(workflow)
        if len(dispatched) == 1:
            raise RuntimeError("dispatch failed")

    monkeypatch.setattr(team, "dispatch", dispatch)
    with pytest.raises(RuntimeError):
        team.autonomous_development("run-1")
    assert not any("genesis-team-autonomous-claim:" in body for _, body in comments)
    team.autonomous_development("run-2")
    assert dispatched == [team.CONFIG["workflows"]["forge"]] * 2
    assert any(n == 867 and "genesis-team-autonomous-claim:" in body for n, body in comments)


@pytest.mark.parametrize("held", ["genesis-waiting-capability", "genesis-verified",
                                  "genesis-repair-in-progress", "genesis-needs-human"])
def test_autonomous_selection_respects_existing_ownership(monkeypatch, held):
    monkeypatch.setattr(team, "open_development_issues", lambda: [
        issue(labels=[{"name": held}]), issue(868)
    ])
    monkeypatch.setattr(team, "autonomous_claim_exists", lambda n: False)
    assert team.select_autonomous_issue()["number"] == 868


def test_autonomous_specialist_reuses_original_issue_and_wakes_executor(monkeypatch):
    calls, comments = [], []

    def request(method, path, payload=None):
        calls.append((method, path, payload))
        if method == "GET":
            return issue()
        return {}

    monkeypatch.setattr(team, "request", request)
    monkeypatch.setattr(team, "comment", lambda n, body: comments.append((n, body)))
    monkeypatch.setattr(team, "provider_reason", lambda *args: ("none", "Pending execution"))
    monkeypatch.setattr(team, "dispatch", lambda *args: None)
    team.agent_run("forge", "Autonomous Genesis development task from issue #867: implement metrics",
                   "autonomous-867-12345", 1000)
    assert [path for method, path, _ in calls if method == "GET"] == ["/issues/867"]
    assert not any(method == "POST" and path == "/issues" for method, path, _ in calls)
    assert any("genesis-agentic-lab-recovery.yml/dispatches" in path for _, path, _ in calls)
    assert any("**Execution issue:** #867" in body for _, body in comments)


@pytest.mark.parametrize("source", [issue(state="closed"), issue(pull_request={"url": "pr"}), issue(1000)])
def test_stale_or_workspace_source_cannot_create_duplicate_task(monkeypatch, source):
    calls = []
    monkeypatch.setattr(team, "request", lambda method, path, payload=None:
                        (calls.append((method, path)), source)[1])
    with pytest.raises(RuntimeError):
        team.create_execution_issue("forge", "implementation", f"autonomous-{source['number']}-run")
    assert len(calls) == 1


def test_team_evolution_reuses_task_after_failed_wake(monkeypatch):
    comments, created, wakes = [], [], []
    monkeypatch.setattr(team, "issue_comments", lambda n: [{"body": body} for _, body in comments])
    monkeypatch.setattr(team, "paged_get", lambda path: created)
    monkeypatch.setattr(team, "comment", lambda n, body: comments.append((n, body)))

    def request(method, path, payload=None):
        created.append({"number": 2000, **payload})
        return created[-1]

    def wake():
        wakes.append(True)
        if len(wakes) == 1:
            raise RuntimeError("wake failed")

    monkeypatch.setattr(team, "request", request)
    monkeypatch.setattr(team, "wake_agentic_lab", wake)
    with pytest.raises(RuntimeError, match="wake failed"):
        team.nexus("Add a new security teammate", "owner", "456")
    assert not team.source_already_processed("456")
    team.nexus("Add a new security teammate", "owner", "456")
    assert len(created) == 1
    assert len(wakes) == 2
    assert team.source_already_processed("456")


@pytest.mark.parametrize("agent", ["atlas", "forge", "scout", "sentinel", "recovery", "nexus"])
def test_workflow_preserves_objective_as_literal_argument(tmp_path, agent):
    workflow = Path(f".github/workflows/genesis-teammate-{agent}.yml").read_text()
    run = textwrap.dedent(workflow.split("        run: |\n", 1)[1])
    assert "${{" not in run
    capture = tmp_path / "argv.json"
    sentinel = tmp_path / "must-not-execute"
    objective = f'--flag "quoted"\n`touch {sentinel}` $(touch {sentinel}) $HOME; résumé'
    stub = tmp_path / "python"
    stub.write_text(f"#!{sys.executable}\nimport json, os, sys\n"
                    "open(os.environ['ARGUMENT_CAPTURE'], 'w').write(json.dumps(sys.argv[1:]))\n")
    stub.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}",
           "ARGUMENT_CAPTURE": str(capture), "OBJECTIVE": objective,
           "SOURCE_COMMENT_ID": "source-123", "NEXUS_ISSUE": "1000",
           "EVENT_NAME": "workflow_dispatch", "MANUAL_OBJECTIVE": objective,
           "OWNER_COMMENT": "", "OWNER_LOGIN": "", "COMMENT_ID": "",
           "ACTOR": "owner", "RUN_ID": "12345"}
    subprocess.run(["bash", "-e", "-c", run], env=env, check=True, timeout=5)
    args = json.loads(capture.read_text())
    assert f"--objective={objective}" in args
    assert not sentinel.exists()
