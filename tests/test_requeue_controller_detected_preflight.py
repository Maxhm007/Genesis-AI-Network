from __future__ import annotations

import scripts.requeue_exhausted_issues as requeue
import genesis.github_issue_detected_reconciler as detected_reconciler


def test_controller_main_runs_satisfied_detector_preflight(monkeypatch, capsys) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("GITHUB_WORKFLOW", "Genesis Sequential Issue Controller")
    monkeypatch.setattr(requeue, "run", lambda repository, token, limit: {"status": "ok", "released": []})

    calls = []

    def reconcile(root):
        calls.append(root)
        return {"status": "ok", "candidate": {"github_issue_number": 560}, "closed": [560]}

    monkeypatch.setattr(detected_reconciler, "reconcile_satisfied_detected_issues", reconcile)

    requeue.main()

    assert calls == [requeue.ROOT]
    output = capsys.readouterr().out
    assert "Satisfied detected regression controller preflight:" in output
    assert '"closed": [' in output


def test_non_controller_requeue_does_not_run_detector_preflight(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("GITHUB_WORKFLOW", "Genesis Exhausted Issue Requeue")
    monkeypatch.setattr(requeue, "run", lambda repository, token, limit: {"status": "ok", "released": []})

    called = False

    def reconcile(root):
        nonlocal called
        called = True
        return {"status": "ok"}

    monkeypatch.setattr(detected_reconciler, "reconcile_satisfied_detected_issues", reconcile)

    requeue.main()

    assert called is False
