from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERAL = ROOT / ".github" / "workflows" / "github-issue-discovery.yml"
CAPABILITY = ROOT / ".github" / "workflows" / "genesis-recent-ai-capability-discovery.yml"
MANAGER = ROOT / ".github" / "workflows" / "genesis-issue-opening-manager.yml"


def _text(path: Path) -> str:
    assert path.is_file(), f"missing workflow: {path.relative_to(ROOT)}"
    return path.read_text(encoding="utf-8")


def test_general_issue_discovery_is_manager_dispatched_and_solver_handoff() -> None:
    text = _text(GENERAL)
    assert "workflow_dispatch:" in text
    assert "schedule:" not in text
    assert "group: genesis-github-issue-discovery-v4" in text
    assert "cancel-in-progress: true" in text
    assert "python scripts/github_issue_discovery_resilient.py" in text
    assert "gh workflow run genesis-agentic-lab-recovery.yml" in text
    assert "timeout-minutes: 35" in text
    assert "GENESIS_DISCOVERY_BATCH_SIZE: '8'" in text
    assert "runtime/github_issue_discovery_cursor.json" in text
    assert "github_issue_autorepair.py" not in text
    assert "genesis-bounded-repair-worker.yml" not in text
    assert "git push origin HEAD:main" not in text


def test_recent_capability_discovery_is_manager_dispatched_and_bounded() -> None:
    text = _text(CAPABILITY)
    assert "workflow_dispatch:" in text
    assert "schedule:" not in text
    assert "group: genesis-recent-ai-capability-discovery" in text
    assert "cancel-in-progress: true" in text
    assert "timeout-minutes: 20" in text
    assert "python scripts/discover_recent_ai_capability.py" in text
    assert "sleep 1800" not in text
    assert "gh workflow run genesis-recent-ai-capability-discovery.yml" not in text
    assert "max_cycles" not in text
    assert "github_issue_autorepair.py" not in text
    assert "git push origin HEAD:main" not in text


def test_capability_discovery_delegates_label_and_issue_authority() -> None:
    text = _text(CAPABILITY)
    assert "issues: read" in text
    assert "issues: write" not in text
    assert "gh label create" not in text
    assert "python scripts/discover_recent_ai_capability.py" in text


def test_issue_opening_manager_is_single_discovery_scheduler() -> None:
    manager = _text(MANAGER)
    assert "cron: '12,42 * * * *'" in manager
    for workflow in (
        "github-issue-discovery.yml",
        "genesis-deepseek-selfdev-discovery.yml",
        "genesis-recent-ai-capability-discovery.yml",
        "genesis-missing-qwen-capability-discovery.yml",
        "genesis-gene-peer-issue-sync.yml",
        "genesis-discovery-silence-watchdog.yml",
    ):
        assert workflow in manager
