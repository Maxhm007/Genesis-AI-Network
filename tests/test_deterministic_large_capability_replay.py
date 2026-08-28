from __future__ import annotations

import json
from pathlib import Path

import pytest

from genesis.coding import CodingModule
from genesis.github_issue_capability_builder import GitHubIssueLearnedCapabilityProvider
from scripts.github_issue_autorepair import propose_issue_repair


TARGET = "genesis/learned_capabilities.py"
MARKER = "# GENESIS_LEARNED_CAPABILITY_INSERTION_POINT"


def _write_large_target(root: Path) -> Path:
    target = root / TARGET
    target.parent.mkdir(parents=True, exist_ok=True)
    padding = "# retained learned capability history\n" + ("# xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n" * 1_100)
    target.write_text(
        "from __future__ import annotations\n\n"
        "def register_capability(name, description, evidence, handler):\n"
        "    return (name, description, evidence, handler)\n\n"
        + padding
        + MARKER
        + "\n",
        encoding="utf-8",
    )
    assert target.stat().st_size > CodingModule.MAX_TOTAL_BYTES
    return target


def _structured_issue() -> dict:
    return {
        "number": 393,
        "title": (
            "[Genesis Task] new capability — Autonomously add one bounded executable Genesis capability "
            "named learned_de5bc409af893198."
        ),
        "user": {"login": "github-actions[bot]"},
        "body": (
            "<!-- genesis-task-id:task-34eddb68a1da0a52 -->\n"
            "- **Task type:** `new_capability`\n"
            "- **Source:** `genesis.evolution_learning`\n"
            "- **Owning module:** `genesis.coding`\n"
            "- **Target:** `genesis/learned_capabilities.py`\n\n"
            "### Objective\n"
            "Autonomously add one bounded executable capability. Use the learned idea: "
            "Add one new bounded Genesis capability implementing this verified transferable lesson: "
            "support webp input through a verified media conversion path. "
            "Acceptance: preserve safeguards. "
            "External learning evidence: upstream release evidence documents webp support via a media conversion path. "
            "Incubator evidence: # GENESIS_LEARNED_CAPABILITY_INSERTION_POINT "
            "Target exactly genesis/learned_capabilities.py.\n\n"
            "### Acceptance\nFull tests and independent validation must pass.\n"
        ),
    }


def test_structured_deterministic_issue_can_replay_when_target_exceeds_model_limit(tmp_path: Path) -> None:
    target = _write_large_target(tmp_path)

    class ModelMustNotRun:
        name = "bounded-model-route"

        def available(self) -> bool:
            return True

        def reason(self, prompt: str) -> str:
            raise AssertionError("model must not run for trusted deterministic capability issues")

    proposal = propose_issue_repair(
        _structured_issue(),
        [TARGET],
        tmp_path,
        provider=ModelMustNotRun(),
    )

    assert proposal.provider == "genesis-deterministic-capability-builder"
    assert set(proposal.files) == {TARGET}
    rendered = proposal.files[TARGET]
    assert len(rendered.encode("utf-8")) > CodingModule.MAX_TOTAL_BYTES
    assert "learned_de5bc409af893198" in rendered
    assert target.read_text(encoding="utf-8") in rendered or MARKER in rendered
    compile(rendered, TARGET, "exec")


def test_generic_model_byte_limit_remains_unchanged(tmp_path: Path) -> None:
    target = _write_large_target(tmp_path)
    coding = CodingModule(tmp_path)

    assert CodingModule.MAX_TOTAL_BYTES == 80_000
    with pytest.raises(ValueError, match="coding proposal exceeds byte limit"):
        coding.validate_proposal(
            {
                "title": "oversized model proposal",
                "rationale": "must remain bounded",
                "files": {TARGET: target.read_text(encoding="utf-8")},
            },
            "bounded-model-route",
        )


def test_trusted_replay_rejects_changes_outside_marker_insertion(tmp_path: Path) -> None:
    target = _write_large_target(tmp_path)
    current = target.read_text(encoding="utf-8")
    proposal = {
        "title": "unsafe deterministic mutation",
        "rationale": "test",
        "files": {TARGET: current.replace("def register_capability", "def replaced_register_capability", 1)},
    }
    provider = GitHubIssueLearnedCapabilityProvider(proposal)

    with pytest.raises(ValueError, match="only insert immediately before the marker"):
        provider.prepare_trusted_full_file_replay(tmp_path, CodingModule(tmp_path))


def test_trusted_replay_rejects_any_second_target(tmp_path: Path) -> None:
    target = _write_large_target(tmp_path)
    current = target.read_text(encoding="utf-8")
    rendered = current.replace(MARKER, "SAFE_INSERT = True\n\n" + MARKER, 1)
    provider = GitHubIssueLearnedCapabilityProvider(
        {
            "title": "unsafe deterministic scope",
            "rationale": "test",
            "files": {TARGET: rendered, "genesis/other.py": "OTHER = True\n"},
        }
    )

    with pytest.raises(ValueError, match="modify only the learned-capability target"):
        provider.prepare_trusted_full_file_replay(tmp_path, CodingModule(tmp_path))


def test_worker_skips_model_stack_only_for_preclassified_deterministic_route() -> None:
    workflow = Path(".github/workflows/github-issue-autorepair-worker.yml").read_text(encoding="utf-8")

    detection = workflow.index("Detect trusted deterministic learned-capability route")
    model_cache = workflow.index("Compute configured repair model cache key")
    assert detection < model_cache
    assert '(.author.login == "github-actions[bot]")' in workflow
    assert 'contains("- **Target:** `genesis/learned_capabilities.py`")' in workflow
    model_condition = "steps.deterministic.outputs.eligible != 'true'"
    assert workflow.count(model_condition) >= 5
    assert "Let Genesis solve the reserved GitHub issue" in workflow
