from pathlib import Path

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
