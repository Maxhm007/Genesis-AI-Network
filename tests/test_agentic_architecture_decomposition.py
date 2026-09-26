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
    monkeypatch.setattr(module, "_derived_safe_target", lambda body: "")
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



def test_workflow_governance_prefers_governor_path_over_generic_source_overlap(tmp_path, monkeypatch):
    governor = tmp_path / "genesis" / "workflow_governor.py"
    governor.parent.mkdir(parents=True)
    governor.write_text(
        "def review_workflows():\n    return ['consolidate', 'disable', 'retire']\n",
        encoding="utf-8",
    )
    noisy = tmp_path / "scripts" / "discover_recent_ai_capability.py"
    noisy.parent.mkdir(parents=True)
    noisy.write_text(
        "workflow capability autonomous issue governance review retire disable\n",
        encoding="utf-8",
    )
    issue = {
        "title": "[Genesis Governance] Let Genesis autonomously review, consolidate, disable and retire GitHub Actions workflows",
        "body": "Continuously govern overlapping and obsolete workflows while protecting validation and owner controls.",
    }
    monkeypatch.setattr(module.agentic, "safe_lane", lambda target: target.startswith(("genesis/", "scripts/")))

    target, score, hits = module._repository_safe_target(issue, root=tmp_path)

    assert target == "genesis/workflow_governor.py"
    assert "workflow" in hits or "governor" in hits


def test_weak_incidental_source_overlap_is_rejected(tmp_path, monkeypatch):
    noisy = tmp_path / "scripts" / "discover_missing_qwen_capability.py"
    noisy.parent.mkdir(parents=True)
    noisy.write_text(
        "credential capability missing secret access worker autonomous issue\n",
        encoding="utf-8",
    )
    issue = {
        "title": "[Genesis Autonomy] Add least-privilege capability and credential manager",
        "body": "Track capability classes and credential requirements without exposing secret values.",
    }
    monkeypatch.setattr(module.agentic, "safe_lane", lambda target: target.startswith(("genesis/", "scripts/")))

    target, score, hits = module._repository_safe_target(issue, root=tmp_path)

    assert target == ""
    assert score >= 0



def test_workflow_governance_prefers_governor_over_discovery_script(tmp_path, monkeypatch):
    governor = tmp_path / "scripts" / "workflow_governor.py"
    governor.parent.mkdir(parents=True)
    governor.write_text(
        "def review_workflows():\n    return 'workflow governance retirement consolidation'\n",
        encoding="utf-8",
    )
    discovery = tmp_path / "scripts" / "discover_recent_ai_capability.py"
    discovery.write_text(
        "def discover():\n    return 'workflow autonomous capability governance issue'\n",
        encoding="utf-8",
    )
    issue = {
        "number": 868,
        "title": "[Genesis Governance] Let Genesis autonomously review, consolidate, disable and retire GitHub Actions workflows",
        "body": "Review overlapping workflows, dead schedules, concurrency conflicts and protected workflows.",
        "labels": [{"name": "genesis-autonomous"}],
    }
    monkeypatch.setattr(module.agentic, "safe_lane", lambda target: target.startswith("scripts/"))

    target, score, hits = module._repository_safe_target(issue, root=tmp_path)

    assert target == "scripts/workflow_governor.py"
    assert score >= 18
    assert "workflow" in hits or "governor" in hits


def test_ambiguous_source_only_match_is_rejected(tmp_path, monkeypatch):
    first = tmp_path / "scripts" / "first.py"
    second = tmp_path / "scripts" / "second.py"
    first.parent.mkdir(parents=True)
    first.write_text("def x():\n    return 'credential capability security autonomous'\n", encoding="utf-8")
    second.write_text("def y():\n    return 'credential capability security autonomous'\n", encoding="utf-8")
    issue = {
        "number": 874,
        "title": "[Genesis Autonomy] Add least-privilege capability and credential manager",
        "body": "Use narrowly scoped credentials and capability classes.",
        "labels": [{"name": "genesis-autonomous"}],
    }
    monkeypatch.setattr(module.agentic, "safe_lane", lambda target: target.startswith("scripts/"))

    target, score, hits = module._repository_safe_target(issue, root=tmp_path)

    assert target == ""


def test_retargets_prior_genesis_inferred_target_when_stronger_match_exists(monkeypatch):
    issue = _issue(868)
    issue["title"] = "[Genesis Governance] Workflow governance"
    issue["body"] += (
        "\n\n### Genesis FIFO decomposition\n"
        "- **Target:** `scripts/discover_recent_ai_capability.py`\n"
        "- **Authority:** This remains the same authoritative Issue; no child or successor Issue is created.\n"
    )
    calls: list[tuple[str, str, dict | None]] = []
    monkeypatch.setattr(module, "_infra_quarantined", lambda repository, token, number: False)
    monkeypatch.setattr(module.agentic, "safe_lane", lambda target: bool(target) and target.startswith("scripts/"))
    monkeypatch.setattr(
        module,
        "_repository_safe_target",
        lambda issue, root=module.ROOT: ("scripts/workflow_governor.py", 60, ["workflow", "governance"]),
    )
    monkeypatch.setattr(module.agentic, "remove_label", lambda *args, **kwargs: None)

    def fake_request(repository, token, method, path, payload=None):
        calls.append((method, path, payload))
        return {}

    monkeypatch.setattr(module.agentic, "request", fake_request)

    result = module._decompose_oldest_issue("owner/repo", "token", [issue])

    assert result["status"] == "retargeted"
    assert result["previous_target"] == "scripts/discover_recent_ai_capability.py"
    assert result["target"] == "scripts/workflow_governor.py"
    patch = next(payload for method, path, payload in calls if method == "PATCH")
    assert "- **Target:** `scripts/workflow_governor.py`" in patch["body"]
