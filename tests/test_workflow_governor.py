from pathlib import Path

from scripts import workflow_governor as runner

from genesis.workflow_governor import (
    Finding,
    PROTECTED_WORKFLOWS,
    analyze,
    choose_autonomous_action,
    remove_schedule_block,
)


def write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_detects_scheduled_worker_that_is_controller_dispatched(tmp_path: Path):
    write(
        tmp_path,
        ".github/workflows/controller.yml",
        """name: Controller
on:
  schedule:
    - cron: '*/10 * * * *'
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - run: gh workflow run worker.yml
""",
    )
    write(
        tmp_path,
        ".github/workflows/worker.yml",
        """name: Repair Worker
on:
  workflow_dispatch:
  schedule:
    - cron: '17,47 * * * *'
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - run: echo repair
""",
    )

    report = analyze(tmp_path)
    matches = [f for f in report.findings if f.kind == "scheduled_dispatch_worker"]
    assert matches
    assert matches[0].workflow.endswith("worker.yml")
    assert matches[0].auto_action == "remove_schedule"


def test_remove_schedule_preserves_other_triggers():
    original = """on:
  workflow_dispatch:
  schedule:
    - cron: '17,47 * * * *'
  issues:
    types: [opened]
"""
    updated = remove_schedule_block(original)
    assert "schedule:" not in updated
    assert "cron:" not in updated
    assert "workflow_dispatch:" in updated
    assert "issues:" in updated


def test_duplicate_scheduled_concurrency_is_reported(tmp_path: Path):
    for name in ("a.yml", "b.yml"):
        write(
            tmp_path,
            f".github/workflows/{name}",
            f"""name: {name}
on:
  schedule:
    - cron: '5 * * * *'
concurrency:
  group: shared-controller
  cancel-in-progress: false
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
""",
        )
    report = analyze(tmp_path)
    assert any(f.kind == "duplicate_concurrency_group" for f in report.findings)


def test_protected_governor_workflows_are_never_selected_for_mutation():
    assert "genesis-workflow-governor.yml" in PROTECTED_WORKFLOWS
    assert "genesis-workflow-governor-validator.yml" in PROTECTED_WORKFLOWS
    report = type("Report", (), {
        "findings": (
            Finding(
                "scheduled_dispatch_worker",
                "medium",
                ".github/workflows/genesis-workflow-governor.yml",
                "x",
                "x",
                "remove_schedule",
            ),
        )
    })()
    action = choose_autonomous_action(report)
    assert action is None


def test_governor_runner_uses_dedicated_workflows_write_token():
    text = (Path(__file__).resolve().parents[1] / "scripts" / "workflow_governor.py").read_text(encoding="utf-8")
    assert 'os.environ.get("GENESIS_WORKFLOW_TOKEN")' in text
    assert 'token = os.environ.get("GENESIS_WORKFLOW_TOKEN")' in text
    assert 'token = os.environ.get("GITHUB_TOKEN")' not in text
    assert 'or os.environ.get("GITHUB_TOKEN")' not in text
    assert 'run("git", "push", push_url, f"HEAD:refs/heads/{branch}", check=False)' in text
    assert "Workflow mutation blocked safely" in text


def test_orphan_candidate_equivalent_to_main_when_changed_blobs_match(monkeypatch):
    monkeypatch.setattr(
        runner,
        "_compare_changed_files",
        lambda branch: [".github/workflows/worker.yml"],
    )

    def fake_sha(ref, path):
        assert path == ".github/workflows/worker.yml"
        return "same-blob"

    monkeypatch.setattr(runner, "_content_sha", fake_sha)

    assert runner.branch_equivalent_to_main(
        "genesis/privileged-candidate-workflow-governor-123-worker"
    )


def test_orphan_candidate_not_equivalent_when_blob_differs(monkeypatch):
    monkeypatch.setattr(
        runner,
        "_compare_changed_files",
        lambda branch: [".github/workflows/worker.yml"],
    )
    monkeypatch.setattr(
        runner,
        "_content_sha",
        lambda ref, path: "main-blob" if ref == "main" else "candidate-blob",
    )

    assert not runner.branch_equivalent_to_main(
        "genesis/privileged-candidate-workflow-governor-123-worker"
    )


def test_orphan_recovery_deletes_superseded_branch_without_opening_pr(monkeypatch):
    monkeypatch.setenv("GENESIS_WORKFLOW_TOKEN", "test-token")
    monkeypatch.setattr(
        runner,
        "governor_candidate_branches",
        lambda: ["genesis/privileged-candidate-workflow-governor-123-worker"],
    )
    monkeypatch.setattr(runner, "_branch_open_pr", lambda branch: None)
    monkeypatch.setattr(runner, "branch_equivalent_to_main", lambda branch: True)
    deleted = []
    monkeypatch.setattr(runner, "delete_governor_branch", deleted.append)
    monkeypatch.setattr(runner, "existing_governor_pr", lambda: None)

    assert runner.recover_orphan_governor_candidates() is None
    assert deleted == ["genesis/privileged-candidate-workflow-governor-123-worker"]
