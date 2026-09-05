from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERAL = ROOT / ".github" / "workflows" / "github-issue-discovery.yml"
CAPABILITY = ROOT / ".github" / "workflows" / "genesis-recent-ai-capability-discovery.yml"


def _text(path: Path) -> str:
    assert path.is_file(), f"missing workflow: {path.relative_to(ROOT)}"
    return path.read_text(encoding="utf-8")


def test_general_issue_discovery_has_native_schedule_and_solver_handoff() -> None:
    text = _text(GENERAL)

    assert "workflow_dispatch:" in text
    assert "schedule:" in text
    assert "cron: '19 * * * *'" in text
    assert "group: genesis-github-issue-discovery" in text
    assert "cancel-in-progress: false" in text
    assert "python scripts/github_issue_discovery.py" in text
    assert "gh workflow run genesis-sequential-issue-controller.yml" in text

    # Discovery is an admission lane, never a second repair/promotion lane.
    assert "github_issue_autorepair.py" not in text
    assert "genesis-bounded-repair-worker.yml" not in text
    assert "git push origin HEAD:main" not in text


def test_recent_capability_discovery_has_native_recovery_schedule() -> None:
    text = _text(CAPABILITY)

    assert "workflow_dispatch:" in text
    assert "schedule:" in text
    assert "cron: '7 */6 * * *'" in text
    assert "group: genesis-recent-ai-capability-discovery" in text
    assert "cancel-in-progress: false" in text
    assert '"$GITHUB_EVENT_NAME" == "schedule"' in text
    assert "python scripts/discover_recent_ai_capability.py" in text
    assert "gh workflow run genesis-recent-ai-capability-discovery.yml" in text

    # The discovery task creates work only; it never implements or closes it.
    assert "github_issue_autorepair.py" not in text
    assert "git push origin HEAD:main" not in text


def test_capability_discovery_label_setup_is_idempotent() -> None:
    text = _text(CAPABILITY)

    assert "gh label create genesis-task" in text
    assert "gh label create genesis-capability-discovery" in text
    assert text.count("--force") >= 2
