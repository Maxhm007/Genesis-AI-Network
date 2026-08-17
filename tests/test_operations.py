from pathlib import Path

from genesis.operations import GenesisOperations


def scorecard(ai=37, samples=0, fresh=True):
    return {
        "ai_capability_score": {"score": ai, "max_score": 100},
        "efficiency_score": {"score": 0, "max_score": 100, "samples": samples},
        "immortality_research_progress_score": {"score": 50, "max_score": 100, "fresh_scan_24h": fresh},
    }


def test_detects_and_queues_measurable_operational_gaps(tmp_path: Path):
    ops = GenesisOperations(tmp_path)
    issues = ops.detect(scorecard())
    titles = {item.title for item in issues}
    assert "AI capability below target" in titles
    assert "Efficiency telemetry insufficient" in titles
    result = ops.persist_and_queue(issues)
    assert len(result["created_tasks"]) == 2
    assert ops.report()["open"] == 2


def test_resolves_issue_when_condition_disappears(tmp_path: Path):
    ops = GenesisOperations(tmp_path)
    ops.persist_and_queue(ops.detect(scorecard(ai=37, samples=0)))
    ops.persist_and_queue(ops.detect(scorecard(ai=75, samples=4)))
    report = ops.report()
    assert report["open"] == 0
    assert report["resolved"] == 2


def test_stale_research_scan_becomes_persistent_task(tmp_path: Path):
    ops = GenesisOperations(tmp_path)
    issues = ops.detect(scorecard(ai=80, samples=4, fresh=False))
    assert len(issues) == 1
    assert issues[0].title == "Immortality research scan stale"
    result = ops.persist_and_queue(issues)
    assert len(result["created_tasks"]) == 1
