from pathlib import Path

from scripts.build_live_status import parse_hourly
from scripts.genesis_hourly_ops import format_capability_evolution_lines


def test_hourly_parser_extracts_capability_evolution_metrics():
    text = """
Genesis Hourly Operations Report
KPI DASHBOARD
AI Capability: 37/100
Efficiency: 0/100 | samples=10 | capability/compute=0.0
Benchmark coverage: measured=2/6 | below_reference=1 | unmeasured=4 | at_or_above=1
Capability growth: active=1 | complete=2 | quarantined=1 | new_capability_tasks=3
Post-promotion impact: improved=1 | no_gain=1 | regressed=0 | awaiting=1
Strategy-change directives: 2 | quarantined_total=11
Development attribution: autonomous=4 | assisted=3 | owner=2 | proven_cycles=9
Persistent tasks: {"assigned": 1, "quarantined": 11}

CAPABILITY EVOLUTION
Benchmark gaps and evidence:
- [GAP:MEASURED_BELOW_REFERENCE] swe_bench_pro | family=software_engineering | actual=60.0 | reference=80.3 percent | capability=software_engineering | target=genesis/coding.py
- [GAP:UNMEASURED] terminal_bench_2_1 | family=long_horizon_tool_coding | actual=unmeasured | reference=91.9 percent | capability=long_horizon_tool_coding | target=genesis/autonomous_engineering.py

Active capability growth:
- [GROWTH:ASSIGNED] task-growth | benchmark=swe_bench_pro | capability=software_engineering | generation=2 | target=genesis/coding.py

New learned capability work:
- [NEW-CAPABILITY:REVIEW] task-learned | capability=memory_learning | target=genesis/learned_capabilities.py

Strategy changes from quarantine learning:
- Strategy change: Do not repeat the same patch; use new evidence.

Post-promotion benchmark impact:
- [IMPACT:IMPROVED] swe_bench_pro | capability=software_engineering | baseline=55.0 | current=60.0 | delta=5.0 | growth_task=task-old

ISSUES: open=1 blocked=0 resolved=1
"""
    parsed = parse_hourly(text)
    evolution = parsed["capability_evolution"]

    assert evolution["coverage"] == {
        "measured": 2,
        "total": 6,
        "below_reference": 1,
        "unmeasured": 4,
        "at_or_above": 1,
    }
    assert evolution["growth"]["active"] == 1
    assert evolution["growth"]["new_capability_tasks"] == 3
    assert evolution["strategy"]["directives"] == 2
    assert evolution["development_attribution"]["autonomous"] == 4
    assert evolution["gaps"][0]["status"] == "measured_below_reference"
    assert evolution["gaps"][1]["actual_score"] is None
    assert evolution["active_growth_tasks"][0]["generation"] == "2"
    assert evolution["new_capabilities"][0]["target_path"] == "genesis/learned_capabilities.py"
    assert evolution["impact_assessments"][0]["delta"] == 5.0


def test_capability_lines_keep_unmeasured_separate_from_measured_deficit():
    snapshot = {
        "status": "ok",
        "gaps": [
            {
                "status": "unmeasured",
                "benchmark_id": "terminal_bench_2_1",
                "family": "long_horizon_tool_coding",
                "actual_score": None,
                "reference_score": 91.9,
                "unit": "percent",
                "capability_key": "long_horizon_tool_coding",
                "target_path": "genesis/autonomous_engineering.py",
            }
        ],
        "active_growth_tasks": [],
        "new_capability_rows": [],
        "quarantine_analysis": {"strategy_directives": []},
        "impact_assessments": [],
    }
    lines = "\n".join(format_capability_evolution_lines(snapshot))
    assert "[GAP:UNMEASURED] terminal_bench_2_1" in lines
    assert "actual=unmeasured" in lines
    assert "Measured deficits are required before capability-growth code is created" in lines


def test_command_center_exposes_evolution_evidence_surfaces():
    html = (Path(__file__).resolve().parents[1] / "docs" / "status" / "index.html").read_text(encoding="utf-8")
    assert "Capability Evolution" in html
    assert 'id="coverage"' in html
    assert 'id="growthList"' in html
    assert 'id="strategyList"' in html
    assert 'id="impactList"' in html
    assert "Verified autonomous promotions" in html
    assert "Evidence gaps, not proven weakness" in html
