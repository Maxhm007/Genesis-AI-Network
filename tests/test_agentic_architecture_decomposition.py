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



def test_revokes_prior_inferred_target_when_semantic_confidence_disappears(monkeypatch):
    issue = _issue(874)
    issue["title"] = "[Genesis Autonomy] Add least-privilege capability and credential manager"
    issue["body"] += (
        "\n\n### Genesis FIFO decomposition\n"
        "- **Target:** `scripts/discover_missing_qwen_capability.py`\n"
        "- **Authority:** This remains the same authoritative Issue; no child or successor Issue is created.\n"
    )
    calls: list[tuple[str, str, dict | None]] = []
    monkeypatch.setattr(module, "_infra_quarantined", lambda repository, token, number: False)
    monkeypatch.setattr(module.agentic, "safe_lane", lambda target: bool(target) and target.startswith("scripts/"))
    monkeypatch.setattr(module, "_repository_safe_target", lambda issue, root=module.ROOT: ("", 13, ["capability"]))
    monkeypatch.setattr(module.agentic, "remove_label", lambda *args, **kwargs: None)

    def fake_request(repository, token, method, path, payload=None):
        calls.append((method, path, payload))
        return {}

    monkeypatch.setattr(module.agentic, "request", fake_request)

    result = module._decompose_oldest_issue("owner/repo", "token", [issue])

    assert result["status"] == "target_revoked"
    assert result["previous_target"] == "scripts/discover_missing_qwen_capability.py"
    patch = next(payload for method, path, payload in calls if method == "PATCH")
    assert "discover_missing_qwen_capability.py" not in patch["body"]
    assert any(
        method == "POST"
        and path == "/issues/874/labels"
        and "genesis-needs-routing" in payload["labels"]
        for method, path, payload in calls
    )



def test_revalidation_ignores_previous_inferred_target_text(monkeypatch):
    issue = _issue(874)
    issue["title"] = "[Genesis Autonomy] Add least-privilege capability and credential manager"
    issue["body"] = (
        "Track narrowly scoped capability classes and credentials without exposing secret values."
        "\n\n### Genesis FIFO decomposition\n"
        "- **Target:** `scripts/discover_missing_qwen_capability.py`\n"
        "- **Authority:** This remains the same authoritative Issue; no child or successor Issue is created.\n"
    )
    calls: list[tuple[str, str, dict | None]] = []
    monkeypatch.setattr(module, "_infra_quarantined", lambda repository, token, number: False)
    monkeypatch.setattr(module.agentic, "safe_lane", lambda target: bool(target) and target.startswith("scripts/"))
    seen = {}

    def fake_score(candidate, root=module.ROOT):
        seen["body"] = candidate["body"]
        return "", 11, ["capability"]

    monkeypatch.setattr(module, "_repository_safe_target", fake_score)
    monkeypatch.setattr(module.agentic, "remove_label", lambda *args, **kwargs: None)

    def fake_request(repository, token, method, path, payload=None):
        calls.append((method, path, payload))
        return {}

    monkeypatch.setattr(module.agentic, "request", fake_request)

    result = module._decompose_oldest_issue("owner/repo", "token", [issue])

    assert "discover_missing_qwen_capability.py" not in seen["body"]
    assert result["status"] == "target_revoked"
    patch = next(payload for method, path, payload in calls if method == "PATCH")
    assert "- **Target:**" not in patch["body"]



def test_unroutable_issue_is_rerouted_instead_of_parked(monkeypatch):
    blocked = _issue(859)
    blocked["labels"].append({"name": "genesis-needs-routing"})
    blocked["body"] += "\n- **Target:** `genesis/old_target.py`\n"

    calls: list[tuple[str, str, dict | None]] = []
    monkeypatch.setattr(module, "_infra_quarantined", lambda repository, token, number: False)
    monkeypatch.setattr(module.agentic, "safe_lane", lambda target: bool(target) and target.startswith(("genesis/", "scripts/")))
    monkeypatch.setattr(module, "_repository_safe_target", lambda issue, root=module.ROOT: ("", 10, ["stale"]))
    monkeypatch.setattr(module.agentic, "remove_label", lambda *args, **kwargs: None)

    def fake_request(repository, token, method, path, payload=None):
        calls.append((method, path, payload))
        return {}

    monkeypatch.setattr(module.agentic, "request", fake_request)

    result = module._decompose_oldest_issue("owner/repo", "token", [blocked])

    assert result["status"] == "retargeted"
    assert result["issue_number"] == 859
    assert result["target"].startswith("genesis/architecture_extensions/")
    patch = next(payload for method, path, payload in calls if method == "PATCH")
    assert result["target"] in patch["body"]
    assert any(
        method == "POST"
        and path == "/issues/859/labels"
        and payload == {"labels": [module.agentic.AGENTIC_LABEL, "genesis-autonomous"]}
        for method, path, payload in calls
    )



def test_actionable_issue_does_not_require_existing_agentic_labels():
    issue = {
        "number": 900,
        "state": "open",
        "title": "[Genesis Test] Unlabeled actionable issue",
        "body": "Implement and verify a repository change.",
        "labels": [],
    }
    assert module._actionable(issue) is True


def test_restore_agentic_visibility_enrolls_unlabeled_actionable_issue(monkeypatch):
    issue = {
        "number": 901,
        "state": "open",
        "title": "[Genesis Test] Enroll me",
        "body": "Implement and verify a repository change.",
        "labels": [],
    }
    calls = []
    monkeypatch.setattr(module, "_infra_quarantined", lambda *args: False)
    monkeypatch.setattr(module.agentic, "remove_label", lambda *args, **kwargs: None)

    def fake_request(repository, token, method, path, payload=None):
        calls.append((method, path, payload))
        return {}

    monkeypatch.setattr(module.agentic, "request", fake_request)
    restored = module._restore_agentic_visibility("owner/repo", "token", [issue])

    assert restored == [901]
    assert any(
        method == "POST"
        and path == "/issues/901/labels"
        and set(payload["labels"]) == {module.agentic.AGENTIC_LABEL, "genesis-autonomous"}
        for method, path, payload in calls
    )



def test_rerouted_architecture_extension_is_not_bounced_back(monkeypatch):
    issue = _issue(858)
    issue["body"] += (
        "\n\n### Genesis FIFO decomposition\n"
        "- **Target:** `genesis/architecture_extensions/route_gene_backlog.py`\n"
        "- **Authority:** This remains the same authoritative Issue; no child or successor Issue is created.\n"
    )
    calls: list[tuple[str, str, dict | None]] = []
    monkeypatch.setattr(module, "_infra_quarantined", lambda *args: False)
    monkeypatch.setattr(module.agentic, "safe_lane", lambda target: bool(target))
    monkeypatch.setattr(
        module.agentic,
        "issue_comments",
        lambda *args: [{"body": "<!-- genesis-agentic-rerouted -->\nprevious target rejected"}],
    )
    monkeypatch.setattr(
        module,
        "_repository_safe_target",
        lambda issue, root=module.ROOT: ("scripts/gene_continuous_work.py", 58, ["gene", "work"]),
    )
    monkeypatch.setattr(module.agentic, "request", lambda *args, **kwargs: calls.append(args[2:]) or {})

    result = module._decompose_oldest_issue("owner/repo", "token", [issue])

    assert result == {"status": "idle", "reason": "no_actionable_fifo_issue"}
    assert not any(call and call[0] == "PATCH" for call in calls)



def test_previously_rejected_target_is_rerouted_even_after_label_was_removed(monkeypatch):
    issue = _issue(858)
    issue["body"] += "\n- **Target:** `scripts/gene_continuous_work.py`\n"
    calls: list[tuple[str, str, dict | None]] = []
    monkeypatch.setattr(module, "_infra_quarantined", lambda *args: False)
    monkeypatch.setattr(
        module.agentic,
        "issue_comments",
        lambda *args: [{
            "body": "<!-- genesis-agentic-rerouted -->\n"
                    "Agentic Lab replaced rejected target `scripts/gene_continuous_work.py` "
                    "with `genesis/architecture_extensions/route_gene_backlog.py`."
        }],
    )
    monkeypatch.setattr(module, "_repository_safe_target", lambda issue, root=module.ROOT: ("scripts/gene_continuous_work.py", 58, ["gene", "work"]))
    monkeypatch.setattr(module.agentic, "safe_lane", lambda target: bool(target))
    monkeypatch.setattr(module.agentic, "remove_label", lambda *args, **kwargs: None)

    def fake_request(repository, token, method, path, payload=None):
        calls.append((method, path, payload))
        return {}

    monkeypatch.setattr(module.agentic, "request", fake_request)

    result = module._decompose_oldest_issue("owner/repo", "token", [issue])

    assert result["status"] == "retargeted"
    assert result["target"].startswith("genesis/architecture_extensions/")
    assert result["target"] != "scripts/gene_continuous_work.py"
