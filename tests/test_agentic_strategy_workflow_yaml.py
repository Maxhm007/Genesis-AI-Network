from pathlib import Path


WORKER = Path(".github/workflows/genesis-agentic-strategy-worker.yml")


def test_agentic_comment_bodies_stay_inside_yaml_run_blocks() -> None:
    text = WORKER.read_text(encoding="utf-8")

    # The prior parser regression placed the second line of a quoted --body
    # argument at YAML column 1, so GitHub rejected the workflow before jobs
    # could be created.
    assert "\nAgentic Lab strategy" not in text
    assert '--body "<!-- genesis-agentic-strategy-result:' not in text


def test_agentic_comments_use_yaml_safe_body_files() -> None:
    text = WORKER.read_text(encoding="utf-8")

    assert text.count("--body-file /tmp/genesis-agentic-") >= 3
    assert "> /tmp/genesis-agentic-declined.md" in text
    assert "> /tmp/genesis-agentic-success.md" in text
    assert "> /tmp/genesis-agentic-failure.md" in text


def test_agentic_strategy_and_safety_gates_are_preserved() -> None:
    text = WORKER.read_text(encoding="utf-8")

    for strategy in (
        "evidence_first",
        "alternative_implementation",
        "diagnostic_reframe",
        "dependency_diagnosis",
    ):
        assert strategy in text

    assert "python -m pytest -q" in text
    assert "python -m genesis.learned_capability_acceptance" in text
    assert "git push origin HEAD:main" in text
    assert "state=closed -f state_reason=completed" in text
    assert "Release unsuccessful Agentic reservation without closing Issue" in text
