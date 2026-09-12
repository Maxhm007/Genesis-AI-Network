from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "park_exhausted_agentic_issues.py"
    spec = importlib.util.spec_from_file_location("park_exhausted_agentic_issues", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_waiting_issue_clears_stale_active_reservation(monkeypatch):
    module = _load_module()
    removed: list[str] = []

    monkeypatch.setattr(
        module,
        "remove_label",
        lambda repository, token, number, label: removed.append(label),
    )

    issue = {
        "number": 707,
        "labels": [
            {"name": "genesis-waiting-user"},
            {"name": "genesis-repair-in-progress"},
            {"name": "genesis-validating"},
            {"name": "agentic-lab"},
        ],
    }

    assert module.park_issue("owner/repo", "token", issue) is False
    assert removed == ["genesis-repair-in-progress", "genesis-validating"]


def test_waiting_issue_without_active_reservation_is_unchanged(monkeypatch):
    module = _load_module()
    removed: list[str] = []

    monkeypatch.setattr(
        module,
        "remove_label",
        lambda repository, token, number, label: removed.append(label),
    )

    issue = {
        "number": 708,
        "labels": [
            {"name": "genesis-waiting-user"},
            {"name": "agentic-lab"},
        ],
    }

    assert module.park_issue("owner/repo", "token", issue) is False
    assert removed == []
