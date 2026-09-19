from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = (
    ROOT / ".github/workflows/genesis-bounded-repair-worker.yml",
    ROOT / ".github/workflows/genesis-agentic-strategy-worker.yml",
    ROOT / ".github/workflows/genesis-deepseek-agentic-solver.yml",
    ROOT / ".github/workflows/genesis-specialist-repair-worker-v2.yml",
)


def test_all_autonomous_repair_lanes_hydrate_verified_memory():
    for path in WORKFLOWS:
        text = path.read_text(encoding="utf-8")
        assert "Hydrate validated Genesis memory" in text, path.name
        assert "python scripts/github_memory_sync.py" in text, path.name


def test_all_verified_repair_lanes_record_memory_before_issue_close():
    for path in WORKFLOWS:
        text = path.read_text(encoding="utf-8")
        record_at = text.index("python scripts/record_verified_repair_memory.py")
        verified_at = text.index("--add-label genesis-verified", record_at)
        close_at = text.index("state=closed", verified_at)
        assert record_at < verified_at < close_at, path.name


def test_memory_recording_occurs_after_post_promotion_full_validation():
    for path in WORKFLOWS:
        text = path.read_text(encoding="utf-8")
        record_at = text.index("python scripts/record_verified_repair_memory.py")
        reset_at = text.rfind("git reset --hard origin/main", 0, record_at)
        full_test_at = text.rfind("python -m pytest -q", reset_at, record_at)
        assert reset_at >= 0 and full_test_at > reset_at, path.name


def test_memory_sync_does_not_replace_normal_validation():
    for path in WORKFLOWS:
        text = path.read_text(encoding="utf-8")
        assert "python -m pytest -q" in text, path.name
        assert "git push origin HEAD:main" in text, path.name
        assert "genesis-verified" in text, path.name



def test_memory_failure_cannot_override_verified_repair_lifecycle():
    for path in WORKFLOWS:
        text = path.read_text(encoding="utf-8")
        assert '|| echo "Verified memory sync unavailable; continue without hydrated memory."' in text, path.name
        assert "if ! python scripts/record_verified_repair_memory.py" in text, path.name
        assert "repair verification remains authoritative" in text, path.name
