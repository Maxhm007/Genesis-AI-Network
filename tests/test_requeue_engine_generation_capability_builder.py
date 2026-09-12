from pathlib import Path

from scripts.requeue_exhausted_issues import ENGINE_PATHS, engine_generation


def _seed_engine_files(root: Path) -> None:
    for relative in ENGINE_PATHS:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"seed:{relative}\n", encoding="utf-8")


def test_capability_builder_is_part_of_repair_engine_generation(tmp_path: Path) -> None:
    assert "genesis/github_issue_capability_builder.py" in ENGINE_PATHS
    _seed_engine_files(tmp_path)
    before = engine_generation(tmp_path)

    builder = tmp_path / "genesis/github_issue_capability_builder.py"
    builder.write_text("changed repair strategy\n", encoding="utf-8")

    assert engine_generation(tmp_path) != before


def test_unrelated_file_does_not_change_repair_engine_generation(tmp_path: Path) -> None:
    _seed_engine_files(tmp_path)
    before = engine_generation(tmp_path)

    unrelated = tmp_path / "docs/unrelated.md"
    unrelated.parent.mkdir(parents=True, exist_ok=True)
    unrelated.write_text("not repair intelligence\n", encoding="utf-8")

    assert engine_generation(tmp_path) == before
