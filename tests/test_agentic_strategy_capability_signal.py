import scripts.agentic_strategy_repair as module


def test_capability_signal_does_not_pause_before_dependency_strategy(monkeypatch, tmp_path):
    monkeypatch.setattr(module.base, "EVIDENCE_PATH", tmp_path / "evidence.json")
    monkeypatch.setattr(module.base, "load_maintainer_repair_guidance", lambda repository, issue_number: "")
    monkeypatch.setattr(
        module.base,
        "run",
        lambda issue_number, repository: {
            "status": "retry_pending",
            "reason": "retry_pending_capability",
        },
    )

    result = module.run(11, "owner/repo", "evidence_first")

    assert result["status"] == "retry_pending"
    assert result["reason"] == "strategy_requires_more_methods"
    assert result["prior_capability_signal"] == "retry_pending_capability"


def test_dependency_strategy_preserves_capability_signal(monkeypatch, tmp_path):
    monkeypatch.setattr(module.base, "EVIDENCE_PATH", tmp_path / "evidence.json")
    monkeypatch.setattr(module.base, "load_maintainer_repair_guidance", lambda repository, issue_number: "")
    monkeypatch.setattr(
        module.base,
        "run",
        lambda issue_number, repository: {
            "status": "retry_pending",
            "reason": "retry_pending_capability",
        },
    )

    result = module.run(12, "owner/repo", "dependency_diagnosis")

    assert result["reason"] == "retry_pending_capability"
    assert "prior_capability_signal" not in result
