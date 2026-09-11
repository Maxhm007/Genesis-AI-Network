from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "discover_missing_qwen_capability.py"
spec = importlib.util.spec_from_file_location("missing_qwen_capability_discovery", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_present_when_expected_module_exists(tmp_path: Path) -> None:
    gap = module.BASELINE[0]
    target = tmp_path / gap.evidence_paths[0]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# bounded implementation\n", encoding="utf-8")
    assert module.capability_present(gap, tmp_path, ()) is True


def test_present_when_registered_learned_capability_matches() -> None:
    gap = module.BASELINE[0]
    assert module.capability_present(gap, Path("/definitely/missing"), ("computer_use_v1",)) is True


def test_missing_without_module_or_registry_evidence(tmp_path: Path) -> None:
    gap = module.BASELINE[0]
    assert module.capability_present(gap, tmp_path, ()) is False


def test_choose_missing_skips_existing_marker(tmp_path: Path) -> None:
    first = module.BASELINE[0]
    marker = f"genesis-missing-capability:{module.fingerprint(first.capability_id)}"
    gap = module.choose_missing(tmp_path, (), [marker])
    assert gap is not None
    assert gap.capability_id != first.capability_id


def test_choose_missing_skips_implemented_capability(tmp_path: Path) -> None:
    first = module.BASELINE[0]
    target = tmp_path / first.evidence_paths[0]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# implementation\n", encoding="utf-8")
    gap = module.choose_missing(tmp_path, (), [])
    assert gap is not None
    assert gap.capability_id != first.capability_id


def test_issue_body_uses_existing_solver_lane_and_distinct_subtype() -> None:
    gap = module.BASELINE[0]
    body = module.issue_body(gap)
    assert "Task type:** `new_capability`" in body
    assert "Capability subtype:** `missing_capability`" in body
    assert "Source:** `genesis.qwen_gap_audit`" in body
    assert "Missing Capability Discovery task only opens the issue" in body


def test_title_remains_compatible_with_existing_capability_builder() -> None:
    gap = module.BASELINE[0]
    title = f"[Genesis Task] new capability — missing baseline: {gap.title}"
    assert title.startswith("[Genesis Task] new capability")


def test_fingerprint_is_stable() -> None:
    assert module.fingerprint("computer_use") == module.fingerprint("computer_use")
    assert module.fingerprint("computer_use") != module.fingerprint("persistent_memory")
