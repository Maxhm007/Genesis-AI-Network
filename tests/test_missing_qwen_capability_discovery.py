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


def test_present_capability_is_not_reported_missing() -> None:
    corpus = "This module provides JSON Schema constrained structured output with schema validation."
    gap = module.BASELINE[0]
    assert module.capability_present(gap, corpus.lower()) is True


def test_choose_missing_skips_existing_marker_and_moves_to_next_gap() -> None:
    first = module.BASELINE[0]
    marker = f"genesis-missing-capability:{module.fingerprint(first.capability_id)}"
    gap = module.choose_missing("", [marker])
    assert gap is not None
    assert gap.capability_id != first.capability_id


def test_choose_missing_skips_repository_capability() -> None:
    first = module.BASELINE[0]
    corpus = "json schema structured output"
    gap = module.choose_missing(corpus, [])
    assert gap is not None
    assert gap.capability_id != first.capability_id


def test_issue_body_uses_existing_solver_lane_and_distinct_subtype() -> None:
    gap = module.BASELINE[0]
    body = module.issue_body(gap)
    assert "Task type:** `new_capability`" in body
    assert "Capability subtype:** `missing_capability`" in body
    assert "Source:** `genesis.qwen_gap_audit`" in body
    assert "Missing Capability Discovery task only opens the issue" in body


def test_fingerprint_is_stable() -> None:
    assert module.fingerprint("computer_use") == module.fingerprint("computer_use")
    assert module.fingerprint("computer_use") != module.fingerprint("persistent_memory")
