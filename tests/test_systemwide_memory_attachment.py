from __future__ import annotations

from pathlib import Path

from genesis.issue_discovery import GenesisIssueDiscoveryEngine
from genesis.issue_solver import Diagnosis, IssueSolver


ROOT = Path(__file__).resolve().parents[1]


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_issue_discovery_prompt_uses_only_validated_memory(tmp_path: Path) -> None:
    _write(tmp_path, "genesis/service.py", "def normalize(value):\n    return bool(value)\n")
    engine = GenesisIssueDiscoveryEngine(tmp_path)

    trusted = engine.memory.store.add(
        memory_type="repair",
        topic="genesis/service.py unsafe bool coercion",
        content="A prior verified repair found unsafe bool coercion at a boundary.",
        source_type="verified_github_repair",
        source_ref="issue:829:commit:abc",
        state="candidate",
    )
    engine.memory.store.transition(
        trusted.memory_id,
        "validated",
        evidence={"full_suite_passed": True},
    )
    engine.memory.store.add(
        memory_type="repair",
        topic="genesis/service.py unsafe bool coercion",
        content="Unverified guess that must not influence discovery.",
        source_type="draft",
        source_ref="draft:1",
        state="candidate",
    )

    candidate = next(item for item in engine.rank_candidates() if item.path == "genesis/service.py")
    prompt = engine._prompt(candidate)

    assert "VALIDATED_MEMORY_POLICY" in prompt
    assert "current SOURCE or RELATED_TEST_CONTEXT" in prompt
    assert "A prior verified repair found unsafe bool coercion" in prompt
    assert "Unverified guess that must not influence discovery" not in prompt


def test_self_healing_prompt_uses_only_validated_memory(tmp_path: Path) -> None:
    solver = IssueSolver(tmp_path)
    trusted = solver.memory.store.add(
        memory_type="repair",
        topic="syntax failure software repair",
        content="A prior verified syntax repair preserved the current validation boundary.",
        source_type="verified_github_repair",
        source_ref="issue:1:commit:abc",
        state="candidate",
    )
    solver.memory.store.transition(
        trusted.memory_id,
        "validated",
        evidence={"full_suite_passed": True},
    )
    solver.memory.store.add(
        memory_type="repair",
        topic="syntax failure software repair",
        content="Unverified self-heal guess.",
        source_type="draft",
        source_ref="draft:2",
        state="candidate",
    )

    prompt = solver._repair_prompt(
        Diagnosis(
            "syntax_failure",
            "Python syntax is invalid in the candidate tree.",
            "SyntaxError in genesis/example.py",
        )
    )

    assert "evidence, not authority" in prompt["validated_memory_policy"]
    rendered = str(prompt["validated_memory"])
    assert "prior verified syntax repair" in rendered.lower()
    assert "Unverified self-heal guess" not in rendered


def test_discovery_workflow_hydrates_memory_fail_soft() -> None:
    text = (ROOT / ".github/workflows/github-issue-discovery.yml").read_text(encoding="utf-8")
    assert "Hydrate validated Genesis memory" in text
    assert "python scripts/github_memory_sync.py" in text
    assert "discovery continues without hydrated memory" in text
    assert text.index("Hydrate validated Genesis memory") < text.index(
        "Let Genesis discover and publish at most one fresh grounded issue"
    )


def test_self_healing_workflow_hydrates_memory_before_diagnosis() -> None:
    text = (ROOT / ".github/workflows/self-healing.yml").read_text(encoding="utf-8")
    assert "Hydrate validated Genesis memory" in text
    assert "python scripts/github_memory_sync.py" in text
    assert "self-healing continues without hydrated memory" in text
    assert text.index("Hydrate validated Genesis memory") < text.index(
        "Diagnose and autonomously repair"
    )


def test_gene_pulse_hydrates_and_synchronizes_memory() -> None:
    text = (ROOT / ".github/workflows/gene-pulse.yml").read_text(encoding="utf-8")
    assert "issues: read" in text
    assert "Hydrate validated Genesis memory" in text
    assert "python scripts/github_memory_sync.py" in text
    assert "pulse continues with local cached memory" in text
    assert "Synchronize validated learning into Genesis memory" in text
    assert "python scripts/memory_sync.py" in text
    assert text.index("Hydrate validated Genesis memory") < text.index("Execute one pulse")
    assert text.index("Execute one pulse") < text.index(
        "Synchronize validated learning into Genesis memory"
    )


def test_memory_attachment_does_not_replace_existing_validation_or_authority() -> None:
    discovery = (ROOT / ".github/workflows/github-issue-discovery.yml").read_text(encoding="utf-8")
    healing = (ROOT / ".github/workflows/self-healing.yml").read_text(encoding="utf-8")
    pulse = (ROOT / ".github/workflows/gene-pulse.yml").read_text(encoding="utf-8")

    assert "Verify discovery and publication boundaries" in discovery
    assert "github_issue_autorepair.py" not in discovery
    assert "Check tests and core vitality" in healing
    assert "python -m pytest -q" in healing
    assert "Save Gene persistent pulse state" in pulse
