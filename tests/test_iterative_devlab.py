from __future__ import annotations

import subprocess
from pathlib import Path

from genesis.devlab.iterative import IterativeGenesisDevLab
from genesis.providers import ProviderRegistry


class RepairingProvider:
    name = "repairing-provider"

    def __init__(self) -> None:
        self.calls = 0
        self.prompts: list[str] = []

    def available(self) -> bool:
        return True

    def reason(self, prompt: str) -> str:
        self.calls += 1
        self.prompts.append(prompt)
        if self.calls == 1:
            return '{"edits":[{"path":"genesis/sample.py","start_line":1,"end_line":1,"new":"VALUE ="}]}'
        return '{"edits":[{"path":"genesis/sample.py","start_line":1,"end_line":1,"new":"VALUE = 2"}]}'


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, text=True, capture_output=True)


def test_iterative_devlab_repairs_failed_trial_before_candidate(tmp_path: Path) -> None:
    (tmp_path / "genesis").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "genesis" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "genesis" / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "tests" / "test_sample.py").write_text(
        "from genesis.sample import VALUE\n\ndef test_value():\n    assert VALUE == 2\n",
        encoding="utf-8",
    )
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.name", "Genesis Test")
    _git(tmp_path, "config", "user.email", "genesis-test@example.invalid")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "baseline")

    provider = RepairingProvider()
    lab = IterativeGenesisDevLab(tmp_path, ProviderRegistry(include_bootstrap=False))
    result = lab.attempt_problem(
        target_path="genesis/sample.py",
        problem="Make VALUE satisfy the existing test",
        acceptance="pytest passes",
        provider=provider,
        provenance={"initiator": "test", "designer": "genesis.devlab"},
    )

    assert provider.calls == 2
    assert "PREVIOUS_TEST_FAILURE" in provider.prompts[1]
    assert result.status == "candidate_created"
    assert result.feedback is not None
    assert result.feedback.tests_passed is True
    assert result.feedback.candidate_created is True
