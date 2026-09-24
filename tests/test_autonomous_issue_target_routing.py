from __future__ import annotations

from pathlib import Path

from genesis.issue_target import extract_issue_target


def test_discovery_issue_target_is_routable():
    body = (
        "Genesis independently discovered this issue from current repository evidence.\n\n"
        "Target: `genesis/github_issue_authority_reconciler.py`\n\n"
        "Observed problem: bool coercion\n"
    )
    assert extract_issue_target(body) == "genesis/github_issue_authority_reconciler.py"


def test_autonomous_controllers_share_canonical_target_parser():
    root = Path(__file__).resolve().parents[1]
    required = (
        ".github/workflows/genesis-bounded-repair-worker.yml",
        ".github/workflows/genesis-agentic-strategy-worker.yml",
    )
    for relative in required:
        text = (root / relative).read_text(encoding="utf-8")
        assert "genesis.issue_target" in text, relative


def test_bounded_worker_does_not_use_legacy_markdown_only_target_parser():
    root = Path(__file__).resolve().parents[1]
    text = (root / ".github/workflows/genesis-bounded-repair-worker.yml").read_text(encoding="utf-8")
    assert "python -m genesis.issue_target" in text
    assert "s/^- \\*\\*Target:" not in text


def test_agentic_dispatch_owns_safe_target_lane_selection():
    root = Path(__file__).resolve().parents[1]
    source = (root / "scripts/agentic_lab_recovery_dispatch.py").read_text(encoding="utf-8")
    assert "def explicit_target" in source
    assert "def safe_lane" in source
    assert 'target.startswith("genesis/")' in source
    assert 'target.startswith("scripts/")' in source
