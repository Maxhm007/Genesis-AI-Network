from pathlib import Path

import pytest

from scripts.deepseek_selfdev_issue_opener import (
    choose_targets,
    extract_json_object,
    fingerprint,
    normalize_proposal,
)


def test_extract_json_object_tolerates_reasoning_prefix():
    value = extract_json_object('thinking first\n{"action":"none","reason":"no grounded issue"}\n')
    assert value["action"] == "none"


def test_choose_targets_is_deterministic_and_bounded():
    paths = [f"genesis/mod_{i}.py" for i in range(10)]
    first = choose_targets(paths, "run-123", limit=4)
    second = choose_targets(paths, "run-123", limit=4)
    assert first == second
    assert len(first) == 4
    assert len(set(first)) == 4


def test_normalize_proposal_requires_exact_grounding(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    target = tmp_path / "genesis" / "sample.py"
    target.write_text("def value():\n    return True\n", encoding="utf-8")
    proposal = normalize_proposal(
        {
            "action": "open_issue",
            "target": "genesis/sample.py",
            "title": "Improve boolean return reliability",
            "finding": "The current return is concrete but this fixture represents a grounded review finding for validation.",
            "evidence": "return True",
            "acceptance": "Implement the bounded improvement and add a focused regression test that proves the intended behavior.",
            "priority": 72,
        },
        tmp_path,
        {"genesis/sample.py"},
    )
    assert proposal is not None
    assert proposal["target"] == "genesis/sample.py"
    assert proposal["priority"] == 72


def test_normalize_proposal_rejects_ungrounded_evidence(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    target = tmp_path / "genesis" / "sample.py"
    target.write_text("def value():\n    return True\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exact substring"):
        normalize_proposal(
            {
                "action": "open_issue",
                "target": "genesis/sample.py",
                "title": "Improve boolean return reliability",
                "finding": "This is a sufficiently specific finding but its evidence is deliberately fabricated for the test.",
                "evidence": "return False",
                "acceptance": "Add a focused regression test and verify the intended behavior without weakening safeguards.",
                "priority": 72,
            },
            tmp_path,
            {"genesis/sample.py"},
        )


def test_fingerprint_changes_when_grounding_changes():
    base = {
        "target": "genesis/sample.py",
        "title": "Improve reliability",
        "finding": "A concrete finding",
        "evidence": "return True",
    }
    changed = dict(base, evidence="return 1")
    assert fingerprint(base) != fingerprint(changed)
