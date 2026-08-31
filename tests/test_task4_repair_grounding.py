from pathlib import Path

from genesis.coding import CodingModule


def test_exact_backtick_fragment_outranks_fuzzy_lines():
    context = {
        "genesis/modules/versioning.py": (
            "def should_rollback(before_percent, after_percent, regression_tolerance=0.0):\n"
            "    # compare scores\n"
            "    return after_percent > before_percent - regression_tolerance\n"
        )
    }
    objective = (
        "Observed defect: `after_percent > before_percent - regression_tolerance`. "
        "Expected behavior: rollback only on a real regression."
    )
    assert CodingModule._best_edit_hint(objective, context) == (
        "genesis/modules/versioning.py",
        3,
    )


def test_retry_prompt_includes_actual_grounded_source_line(tmp_path: Path):
    target = tmp_path / "genesis" / "modules" / "versioning.py"
    target.parent.mkdir(parents=True)
    target.write_text(
        "def should_rollback(before_percent, after_percent, regression_tolerance=0.0):\n"
        "    return after_percent > before_percent - regression_tolerance\n",
        encoding="utf-8",
    )
    coding = object.__new__(CodingModule)
    coding.root = tmp_path
    prompt = coding._repair_prompt(
        "ORIGINAL",
        '{"edits":[]}',
        ValueError("invalid Python syntax"),
        1,
        ("genesis/modules/versioning.py",),
        ("genesis/modules/versioning.py", 2),
    )
    assert "GROUNDED_SOURCE_LINE:     return after_percent > before_percent - regression_tolerance" in prompt
    assert "preserve required leading syntax such as return" in prompt
