from pathlib import Path

import pytest

from genesis.autonomy_guard import AutonomyGuard
from genesis.selfdev import normalize_selfdev_path


def test_normal_candidate_remains_autonomous(tmp_path: Path):
    decision = AutonomyGuard(tmp_path).analyze(["genesis/example.py"], "+safe = True")
    assert decision.level == "normal"
    assert decision.autonomous_allowed is True
    assert decision.owner_escalation_required is False


def test_workflow_change_uses_privileged_autonomy_without_owner_by_default(tmp_path: Path):
    decision = AutonomyGuard(tmp_path).analyze(
        [".github/workflows/self-healing.yml"],
        "+permissions:\n+  contents: read\n",
    )
    assert decision.level == "privileged"
    assert decision.autonomous_allowed is True
    assert decision.owner_escalation_required is False
    assert AutonomyGuard.proposal_requires_privileged_lane(decision.changed_files)


def test_root_autonomy_gate_change_requires_owner_escalation(tmp_path: Path):
    decision = AutonomyGuard(tmp_path).analyze(
        [".github/workflows/candidate-pr-gate.yml"],
        "+permissions:\n+  contents: write\n",
    )
    assert decision.level == "high_risk"
    assert decision.autonomous_allowed is False
    assert decision.owner_escalation_required is True
    assert decision.risk_score >= 60


def test_constitution_and_genesis_block_remain_immutable(tmp_path: Path):
    decision = AutonomyGuard(tmp_path).analyze(["GENESIS_CONSTITUTION.md"], "+change")
    assert decision.level == "immutable"
    assert decision.risk_score == 100
    assert decision.autonomous_allowed is False
    assert decision.owner_escalation_required is True


def test_selfdev_path_parser_requires_explicit_privileged_opt_in(tmp_path: Path):
    with pytest.raises(RuntimeError, match="privileged autonomy lane"):
        normalize_selfdev_path(tmp_path, ".github/workflows/self-healing.yml")
    assert (
        normalize_selfdev_path(
            tmp_path,
            ".github/workflows/self-healing.yml",
            allow_privileged=True,
        )
        == ".github/workflows/self-healing.yml"
    )
    with pytest.raises(RuntimeError, match="protected path"):
        normalize_selfdev_path(tmp_path, "GENESIS_BLOCK.json", allow_privileged=True)
