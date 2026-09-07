import scripts.agentic_strategy_repair as module


def test_strategy_runner_injects_materially_different_guidance(monkeypatch, tmp_path):
    captured: dict[str, str] = {}

    monkeypatch.setattr(module.base, "EVIDENCE_PATH", tmp_path / "evidence.json")
    monkeypatch.setattr(module.base, "MAX_MAINTAINER_GUIDANCE_CHARS", 3000)
    monkeypatch.setattr(module.base, "load_maintainer_repair_guidance", lambda repository, issue_number: "existing maintainer guidance")

    def fake_run(issue_number, repository):
        captured["guidance"] = module.base.load_maintainer_repair_guidance(repository, issue_number)
        return {"status": "retry_pending", "reason": "repair_failed_validation"}

    monkeypatch.setattr(module.base, "run", fake_run)

    result = module.run(7, "owner/repo", "alternative_implementation")

    assert result["agentic_strategy"] == "alternative_implementation"
    assert "existing maintainer guidance" in captured["guidance"]
    assert "materially different implementation path" in captured["guidance"]


def test_dependency_strategy_explicitly_allows_capability_diagnosis():
    guidance = module.STRATEGY_GUIDANCE["dependency_diagnosis"]
    assert "repair capability" in guidance
    assert "provider/tooling limitation" in guidance
    assert "orchestration layer will open a capability-building dependency issue" in guidance
