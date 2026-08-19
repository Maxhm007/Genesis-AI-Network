from pathlib import Path

import pytest

from genesis.devlab.iterative import IterativeGenesisDevLab


def test_ephemeral_acceptance_files_are_installed_only_under_tests(tmp_path):
    installed = IterativeGenesisDevLab._install_ephemeral_files(
        tmp_path,
        {"tests/test_acceptance_example.py": "def test_ok():\n    assert True\n"},
    )

    assert installed == ("tests/test_acceptance_example.py",)
    assert (tmp_path / "tests" / "test_acceptance_example.py").read_text(encoding="utf-8").startswith("def test_ok")


@pytest.mark.parametrize(
    "path",
    [
        "genesis/test_escape.py",
        "tests/helper.py",
        "tests/test_escape.txt",
        "../tests/test_escape.py",
        "/tmp/test_escape.py",
    ],
)
def test_ephemeral_acceptance_files_reject_paths_outside_bounded_test_namespace(tmp_path, path):
    with pytest.raises(ValueError):
        IterativeGenesisDevLab._install_ephemeral_files(tmp_path, {path: "def test_x():\n    assert True\n"})


def test_ephemeral_acceptance_files_enforce_file_and_byte_budgets(tmp_path):
    too_many = {f"tests/test_acceptance_{index}.py": "def test_x():\n    assert True\n" for index in range(5)}
    with pytest.raises(ValueError, match="too many"):
        IterativeGenesisDevLab._install_ephemeral_files(tmp_path, too_many)

    with pytest.raises(ValueError, match="bounded size"):
        IterativeGenesisDevLab._install_ephemeral_files(
            tmp_path,
            {"tests/test_large_acceptance.py": "x" * (IterativeGenesisDevLab.MAX_EPHEMERAL_BYTES + 1)},
        )
