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
    monkeypatch.setattr(module, "_close_if_legacy_performance_indicator", lambda issue_number, repository: None)
    monkeypatch.setattr(module, "_close_if_current_main_satisfies", lambda issue_number, repository: None)
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


def test_benchmark_runner_satisfaction_requires_existing_adapter_and_route(tmp_path):
    (tmp_path / "genesis").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "genesis" / "benchmark_execution.py").write_text(
        'from .swe_bench_pro_evidence import SWEBenchProEvidenceAdapter\n'
        'EVIDENCE_ADAPTER_BENCHMARKS = {"swe_bench_pro"}\n'
        'def advance(self, benchmark_id, input_path, job):\n'
        '    if benchmark_id == "swe_bench_pro" and input_path.is_file():\n'
        '        return SWEBenchProEvidenceAdapter(self.root).stage(job)\n',
        encoding="utf-8",
    )
    (tmp_path / "genesis" / "swe_bench_pro_evidence.py").write_text(
        'class SWEBenchProEvidenceAdapter:\n    pass\n',
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_benchmark_execution.py").write_text(
        'def test_swe_bench_pro_route():\n    assert "swe_bench_pro"\n',
        encoding="utf-8",
    )
    issue = {
        "state": "open",
        "body": (
            '- **Task type:** `benchmark_runner_integration`\n'
            '- **Target:** `genesis/benchmark_execution.py`\n'
            'Make benchmark swe_bench_pro executable for Genesis using the official/comparable benchmark runner.\n'
        ),
    }

    result = module._benchmark_runner_satisfaction(issue, tmp_path)

    assert result is not None
    assert result["benchmark_id"] == "swe_bench_pro"
    assert result["adapter"] == "SWEBenchProEvidenceAdapter"


def test_agentic_lab_closes_already_satisfied_benchmark_after_full_suite(monkeypatch, tmp_path):
    (tmp_path / "genesis").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "genesis" / "benchmark_execution.py").write_text(
        'from .swe_bench_pro_evidence import SWEBenchProEvidenceAdapter\n'
        'EVIDENCE_ADAPTER_BENCHMARKS = {"swe_bench_pro"}\n'
        'def advance(self, benchmark_id, input_path, job):\n'
        '    if benchmark_id == "swe_bench_pro" and input_path.is_file():\n'
        '        return SWEBenchProEvidenceAdapter(self.root).stage(job)\n',
        encoding="utf-8",
    )
    (tmp_path / "genesis" / "swe_bench_pro_evidence.py").write_text(
        'class SWEBenchProEvidenceAdapter:\n    pass\n',
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_benchmark_execution.py").write_text(
        'def test_swe_bench_pro_route():\n    assert True\n',
        encoding="utf-8",
    )
    issue = {
        "state": "open",
        "body": (
            '- **Task type:** `benchmark_runner_integration`\n'
            '- **Target:** `genesis/benchmark_execution.py`\n'
            'Make benchmark swe_bench_pro executable for Genesis using the official/comparable benchmark runner.\n'
        ),
    }
    calls: list[tuple[str, str, object]] = []

    def fake_api(method, url, payload=None):
        calls.append((method, url, payload))
        if method == "GET":
            return issue
        if method == "PATCH":
            return {"state": "closed"}
        return {}

    label_calls: list[dict] = []
    monkeypatch.setattr(module.base, "_api_json", fake_api)
    monkeypatch.setattr(module.base, "_set_labels", lambda repository, issue_number, **kwargs: label_calls.append(kwargs))
    monkeypatch.setattr(module, "_full_suite_passes", lambda root: (True, "1129 passed, 41 skipped"))

    result = module._close_if_current_main_satisfies(350, "owner/repo", tmp_path)

    assert result is not None
    assert result["status"] == "completed"
    assert result["reason"] == "current_main_already_satisfies_issue"
    assert result["full_suite_verified"] is True
    assert label_calls[0]["add"] == ("genesis-verified",)
    assert any(method == "POST" and str(url).endswith("/comments") for method, url, _ in calls)
    assert any(method == "PATCH" and payload == {"state": "closed", "state_reason": "completed"} for method, _, payload in calls)


def test_agentic_lab_terminally_closes_legacy_capability_growth_as_performance_indicator(monkeypatch):
    issue = {
        "state": "open",
        "title": "Genesis Control: Capability Growth — software_engineering / swe_bench_pro / generation 6",
        "body": (
            "<!-- genesis-capability-source:task-9cdb99cf5204434c -->\n"
            "- **Benchmark:** `swe_bench_pro`\n"
            "- **Validated baseline:** 0.0 percent\n"
            "- **Reference:** 80.3 percent\n\n"
            "### Objective\n"
            "Improve the measured Genesis capability gap for benchmark swe_bench_pro.\n"
        ),
    }
    calls: list[tuple[str, str, object]] = []

    def fake_api(method, url, payload=None):
        calls.append((method, url, payload))
        if method == "GET":
            return issue
        if method == "PATCH":
            return {"state": "closed"}
        return {}

    monkeypatch.setattr(module.base, "_api_json", fake_api)

    result = module._close_if_legacy_performance_indicator(336, "owner/repo")

    assert result is not None
    assert result["status"] == "completed"
    assert result["classification"] == "performance-indicator"
    assert result["closure_state_reason"] == "not_planned"
    patches = [payload for method, _, payload in calls if method == "PATCH"]
    assert patches
    assert patches[-1]["state"] == "closed"
    assert patches[-1]["state_reason"] == "not_planned"
    assert patches[-1]["labels"] == ["performance-indicator"]
    assert patches[-1]["title"].startswith("[Performance Indicator]")
