from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from scripts import self_heal


def test_exhausted_repair_does_not_rerun_team(monkeypatch):
    class UnexpectedTeam:
        def __init__(self, *args, **kwargs):
            raise AssertionError("exhausted repair must not restart an AI team")
    monkeypatch.setattr(self_heal, "AITeam", UnexpectedTeam)
    attempt = SimpleNamespace(status="escalation_required")
    assert self_heal.run_issue_team(attempt) == []


def test_escalation_without_github_credentials_is_safe(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr(self_heal, "__file__", str(tmp_path / "scripts" / "self_heal.py"))
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    fake = SimpleNamespace(
        status="escalation_required",
        diagnosis=SimpleNamespace(category="import_failure", summary="Missing dependency", failure_text="E   ImportError: missing"),
        proposal=None,
        result=None,
    )
    monkeypatch.setattr(self_heal, "IssueSolver", lambda root: SimpleNamespace(solve_once=lambda: fake))
    monkeypatch.setattr(self_heal, "run_issue_team", lambda attempt: [])
    monkeypatch.setattr(self_heal.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not call gh")))
    self_heal.main()
    assert "escalation_not_published" in capsys.readouterr().out
