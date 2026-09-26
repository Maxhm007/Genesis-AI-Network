from __future__ import annotations

import scripts.agentic_lab_capability_first_dispatch as module


def _issue(number: int = 857) -> dict:
    return {
        "number": number,
        "state": "open",
        "title": "[Genesis Architecture] Prioritize capability blockers by number of parent issues unlocked",
        "body": (
            "Build a dependency-aware scheduler for reusable capability blockers. "
            "Rank capability blockers by blocked parents, priority, age, retry depth and reuse."
        ),
        "labels": [{"name": "genesis-autonomous"}, {"name": "genesis-architecture-route"}],
    }


def test_repository_safe_target_uses_issue_semantics(tmp_path, monkeypatch):
    capability = tmp_path / "scripts" / "capability_issue_priority_dispatch.py"
    capability.parent.mkdir(parents=True)
    capability.write_text(
        "def rank_capability_blockers(blocked_parents, retry_depth, reuse_value):\n"
        "    return blocked_parents + retry_depth + reuse_value\n",
        encoding="utf-8",
    )
    unrelated = tmp_path / "genesis" / "dashboard.py"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("def render_dashboard():\n    return 'ok'\n", encoding="utf-8")

    monkeypatch.setattr(module.agentic, "safe_lane", lambda target: target.startswith(("genesis/", "scripts/")))

    target, score, hits = module._repository_safe_target(_issue(), root=tmp_path)

    assert target == "scripts/capability_issue_priority_dispatch.py"
    assert score >= 8
    assert "capability" in hits or "blockers" in hits


def test_targetless_architecture_issue_is_decomposed_on_same_issue(monkeypatch):
    issue = _issue()
    calls: list[tuple[str, str, dict | None]] = []

    monkeypatch.setattr(module, "_infra_quarantined", lambda repository, token, number: False)
    monkeypatch.setattr(module, "_derived_safe_target", lambda body: "")
    monkeypatch.setattr(
        module,
        "_repository_safe_target",
        lambda issue, root=module.ROOT: (
            "scripts/capability_issue_priority_dispatch.py",
            24,
            ["capability", "priority", "blocked"],
        ),
    )
    monkeypatch.setattr(module.agentic, "issue_comments", lambda repository, token, number: [])
    monkeypatch.setattr(module.agentic, "safe_lane", lambda target: target.startswith(("genesis/", "scripts/")))
    monkeypatch.setattr(module.agentic, "remove_label", lambda *args, **kwargs: None)

    def fake_request(repository, token, method, path, payload=None):
        calls.append((method, path, payload))
        return {}

    monkeypatch.setattr(module.agentic, "request", fake_request)

    result = module._decompose_oldest_issue("owner/repo", "token", [issue])

    assert result == {
        "status": "decomposed",
        "issue_number": 857,
        "target": "scripts/capability_issue_priority_dispatch.py",
    }

    patch = next(payload for method, path, payload in calls if method == "PATCH" and path == "/issues/857")
    assert "- **Target:** `scripts/capability_issue_priority_dispatch.py`" in patch["body"]
    assert "same authoritative Issue" in patch["body"]
    assert any(
        method == "POST"
        and path == "/issues/857/labels"
        and payload == {"labels": [module.agentic.AGENTIC_LABEL, "genesis-autonomous"]}
        for method, path, payload in calls
    )
    comment = next(
        payload["body"]
        for method, path, payload in calls
        if method == "POST" and path == "/issues/857/comments"
    )
    assert "Repository inference score: 24" in comment
    assert "capability, priority, blocked" in comment



def test_decomposition_skips_routable_issue_and_advances_next_targetless(monkeypatch):
    routable = _issue(857)
    routable["body"] += "\n- **Target:** `scripts/capability_issue_priority_dispatch.py`\n"
    targetless = _issue(858)
    targetless["title"] = "[Genesis Architecture] Route backlog work to idle Genes"

    calls: list[tuple[str, str, dict | None]] = []
    monkeypatch.setattr(module, "_infra_quarantined", lambda repository, token, number: False)
    monkeypatch.setattr(module.agentic, "safe_lane", lambda target: bool(target) and target.startswith(("genesis/", "scripts/")))
    monkeypatch.setattr(module, "_derived_safe_target", lambda body: "" if "idle Genes" in body else "scripts/capability_issue_priority_dispatch.py")
    monkeypatch.setattr(
        module,
        "_repository_safe_target",
        lambda issue, root=module.ROOT: (
            "scripts/agentic_parallel_dispatch.py",
            20,
            ["route", "backlog", "parallel"],
        ),
    )
    monkeypatch.setattr(module.agentic, "issue_comments", lambda repository, token, number: [])
    monkeypatch.setattr(module.agentic, "remove_label", lambda *args, **kwargs: None)

    def fake_request(repository, token, method, path, payload=None):
        calls.append((method, path, payload))
        return {}

    monkeypatch.setattr(module.agentic, "request", fake_request)

    result = module._decompose_oldest_issue("owner/repo", "token", [routable, targetless])

    assert result["status"] == "decomposed"
    assert result["issue_number"] == 858
    assert result["target"] == "scripts/agentic_parallel_dispatch.py"
    assert any(method == "PATCH" and path == "/issues/858" for method, path, _ in calls)
    assert not any(method == "PATCH" and path == "/issues/857" for method, path, _ in calls)
