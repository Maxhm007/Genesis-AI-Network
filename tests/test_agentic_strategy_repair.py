from pathlib import Path

import pytest
import scripts.agentic_strategy_repair as module
from genesis.selfdev import SelfDevelopmentExecutor, normalize_selfdev_path
from genesis.coding import CodingModule
from genesis.system_issue_repair_policy import _proposal_with_privilege_anchor


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


def test_navigation_landmark_micro_repair_builds_one_safe_candidate(tmp_path):
    target = tmp_path / "scripts" / "self_evaluation_dashboard.py"
    target.parent.mkdir(parents=True)
    target.write_text(
        'from pathlib import Path\n\nDASHBOARD = Path("docs/status/index.html")\n\ndef patch_dashboard():\n'
        '    html = DASHBOARD.read_text(encoding="utf-8")\n'
        '    DASHBOARD.write_text(html, encoding="utf-8")\n',
        encoding="utf-8",
    )
    issue = {
        "title": "Label the dashboard navigation landmark",
        "body": (
            "Target: `scripts/self_evaluation_dashboard.py`\n"
            "Evidence: The primary <nav class=\"nav\"> landmark has no aria-label."
        ),
    }

    proposal = module._navigation_landmark_micro_repair(
        issue,
        ["scripts/self_evaluation_dashboard.py"],
        tmp_path,
    )

    assert proposal is not None
    assert proposal.provider == "genesis-agentic-micro-repair"
    assert set(proposal.files) == {"scripts/self_evaluation_dashboard.py"}
    rendered = proposal.files["scripts/self_evaluation_dashboard.py"]
    assert '<nav class="nav" aria-label="Dashboard navigation">' in rendered
    assert rendered.count("html = html.replace(") == 1
    assert module._explicit_safe_script_paths(issue["body"], tmp_path) == list(proposal.files)
    SelfDevelopmentExecutor(tmp_path)._validate_paths(list(proposal.files))
    CodingModule(tmp_path).validate_proposal({"files": proposal.files}, proposal.provider)
    assert _proposal_with_privilege_anchor(SelfDevelopmentExecutor(tmp_path), {"files": proposal.files}) == {"files": proposal.files}


@pytest.mark.parametrize("target", ["scripts/arbitrary.py", "scripts/secret_guard.py",
    "scripts/privileged_change_gate.py", "scripts/verify_validator_votes.py",
    "scripts/action_repair_guard.py", "scripts/issue_acceptance_guard.py",
    "scripts/../scripts/self_evaluation_dashboard.py"])
def test_script_router_and_executor_reject_unapproved_paths(tmp_path, target):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / Path(target).name).write_text("pass\n", encoding="utf-8")
    assert module._explicit_safe_script_paths(f"Target: `{target}`", tmp_path) == []
    with pytest.raises(RuntimeError):
        normalize_selfdev_path(tmp_path, target)


def test_dashboard_script_router_rejects_symlink_escape(tmp_path):
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    outside = tmp_path / "outside.py"
    outside.write_text("pass\n", encoding="utf-8")
    target = root / "scripts" / "self_evaluation_dashboard.py"
    try:
        target.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation unavailable")
    assert module._explicit_safe_script_paths("scripts/self_evaluation_dashboard.py", root) == []
    with pytest.raises(RuntimeError, match="outside repository"):
        normalize_selfdev_path(root, "scripts/self_evaluation_dashboard.py")


def test_navigation_landmark_micro_repair_refuses_protected_or_ambiguous_targets(tmp_path):
    protected = tmp_path / "scripts" / "secret_guard.py"
    protected.parent.mkdir(parents=True)
    protected.write_text('    html = DASHBOARD.read_text(encoding="utf-8")\n', encoding="utf-8")
    issue = {
        "title": "Label the dashboard navigation landmark",
        "body": "The navigation landmark has no aria-label.",
    }

    assert module._navigation_landmark_micro_repair(issue, ["scripts/secret_guard.py"], tmp_path) is None
    assert module._navigation_landmark_micro_repair(
        issue,
        ["scripts/a.py", "scripts/b.py"],
        tmp_path,
    ) is None
