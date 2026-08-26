from __future__ import annotations

import json
from pathlib import Path

from genesis.coding import CodingModule
from genesis.github_issue_capability_builder import GitHubIssueLearnedCapabilityProvider
from genesis.selfdev import SelfDevResult
from scripts.github_issue_autorepair import solve_reported_issue


def _write_target(root: Path) -> None:
    target = root / "genesis" / "learned_capabilities.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "from __future__ import annotations\n\n"
        "def register_capability(name, description, evidence, handler):\n"
        "    return (name, description, evidence, handler)\n\n"
        "# GENESIS_LEARNED_CAPABILITY_INSERTION_POINT\n",
        encoding="utf-8",
    )


def _issue(*, author: str = "github-actions[bot]", lesson: str | None = None) -> dict:
    learned = lesson or (
        "Add one new bounded Genesis capability implementing this verified transferable lesson: "
        "build UI once and reuse the artifact in release jobs; consume a prebuilt artifact instead of rebuilding it."
    )
    return {
        "number": 453,
        "title": (
            "[Genesis Task] new capability — Autonomously add one bounded executable Genesis capability "
            "named learned_85ee71b19ede1785."
        ),
        "user": {"login": author},
        "body": (
            "<!-- genesis-task-id:task-c84468d330737aeb -->\n"
            "Genesis-Problem-Fingerprint: genesis-task:task-c84468d330737aeb\n"
            "- **Task type:** `new_capability`\n"
            "- **Source:** `genesis.evolution_learning`\n"
            "- **Owning module:** `genesis.coding`\n"
            "- **Target:** `genesis/learned_capabilities.py`\n\n"
            "### Objective\n"
            f"Autonomously add a capability. Use the learned idea: {learned} "
            "Acceptance: preserve safeguards. "
            "External learning evidence: CI builds the UI once, publishes llama-ui.zip, and server jobs reuse/extract "
            "the prebuilt ui-build artifact instead of npm-building the UI. "
            "* Incubator evidence: # GENESIS_LEARNED_CAPABILITY_INSERTION_POINT "
            "Target exactly genesis/learned_capabilities.py.\n\n"
            "### Acceptance\nFull tests and independent validation must pass.\n"
        ),
    }


def test_machine_generated_build_once_issue_uses_deterministic_template(tmp_path: Path) -> None:
    _write_target(tmp_path)
    provider = GitHubIssueLearnedCapabilityProvider.for_issue(
        tmp_path,
        _issue(),
        CodingModule(tmp_path),
    )

    assert provider is not None
    assert provider.name == "genesis-deterministic-capability-builder"
    proposal = json.loads(provider.reason("ignored"))
    rendered = proposal["files"]["genesis/learned_capabilities.py"]
    assert "reusable_build_artifact_85ee71b19ede" in rendered
    assert "request a build only when it is missing" in rendered
    compile(rendered, "genesis/learned_capabilities.py", "exec")

    namespace: dict[str, object] = {}
    exec(rendered, namespace)
    handler = namespace["_learned_85ee71b19ede"]
    assert handler("llama-ui.zip", ["backend.zip", "llama-ui.zip"]) == ("llama-ui.zip", False)
    assert handler("llama-ui.zip", ["backend.zip"]) == ("llama-ui.zip", True)
    assert handler("llama-ui.zip", ["backend.zip"], False) == ("llama-ui.zip", False)


def test_user_authored_issue_cannot_select_machine_deterministic_route(tmp_path: Path) -> None:
    _write_target(tmp_path)

    provider = GitHubIssueLearnedCapabilityProvider.for_issue(
        tmp_path,
        _issue(author="Maxhm007"),
        CodingModule(tmp_path),
    )

    assert provider is None


def test_unsupported_machine_lesson_falls_back_instead_of_inventing_template(tmp_path: Path) -> None:
    _write_target(tmp_path)

    provider = GitHubIssueLearnedCapabilityProvider.for_issue(
        tmp_path,
        _issue(lesson="A verified transferable lesson about an unrelated unknown transform."),
        CodingModule(tmp_path),
    )

    assert provider is None


def test_github_issue_solver_prefers_deterministic_builder_before_qwen(tmp_path: Path) -> None:
    _write_target(tmp_path)
    (tmp_path / "runtime").mkdir()

    class QwenMustNotRun:
        name = "qwen2.5-coder-0.5b-github-issue-autorepair"

        def available(self) -> bool:
            return True

        def reason(self, prompt: str) -> str:
            raise AssertionError("Qwen must not run for a supported machine-generated capability issue")

    class PassingExecutor:
        def __init__(self) -> None:
            self.proposal: dict | None = None

        def execute(self, proposal: dict) -> SelfDevResult:
            self.proposal = proposal
            return SelfDevResult(
                branch="genesis/candidate-live-capability",
                candidate_id="live-capability",
                tests_passed=True,
                committed=True,
                changed_files=("genesis/learned_capabilities.py",),
                commit_sha="a" * 40,
                message="candidate ready",
            )

    executor = PassingExecutor()
    attempt = solve_reported_issue(
        _issue(),
        tmp_path,
        provider=QwenMustNotRun(),
        executor=executor,
        repair_memory=[],
    )

    assert attempt.status == "candidate_repaired"
    assert executor.proposal is not None
    assert executor.proposal["provenance"]["provider"] == "genesis-deterministic-capability-builder"
    rendered = executor.proposal["files"]["genesis/learned_capabilities.py"]
    assert "reusable_build_artifact_85ee71b19ede" in rendered
