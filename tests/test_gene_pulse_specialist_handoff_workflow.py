from __future__ import annotations

from pathlib import Path


def _workflow() -> str:
    return (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "gene-pulse.yml").read_text(encoding="utf-8")


def test_gene_pulse_detects_and_dispatches_specialist_proactive_handoff() -> None:
    text = _workflow()

    assert "- name: Detect pending specialist Proactive handoff" in text
    assert 'run: python scripts/specialist_handoff_gate.py --github-output "$GITHUB_OUTPUT"' in text
    assert "- name: Yield next autonomous slot to specialist Proactive lane" in text
    assert "if: steps.specialist_handoff.outputs.pending == 'true'" in text
    assert "gh workflow run proactive-development.yml" in text
    assert "--repo \"$GITHUB_REPOSITORY\"" in text
    assert "--ref main" in text


def test_pending_specialist_handoff_suppresses_other_self_dispatches() -> None:
    text = _workflow()

    provider_condition = (
        "if: steps.specialist_handoff.outputs.pending != 'true' && "
        "steps.provider_gate.outputs.needs_local_provider == 'true'"
    )
    pulse_condition = (
        "if: steps.specialist_handoff.outputs.pending != 'true' && "
        "steps.provider_gate.outputs.needs_local_provider != 'true'"
    )
    assert provider_condition in text
    assert pulse_condition in text


def test_shared_autonomous_single_lane_is_preserved() -> None:
    text = _workflow()

    assert "group: genesis-autonomous-single-lane" in text
    assert "cancel-in-progress: false" in text
