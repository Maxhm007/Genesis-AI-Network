from pathlib import Path

from genesis.email_reporter import GenesisEmailReporter
from genesis.modules.task_queue import PersistentTaskQueue


def test_email_reporter_uses_runtime_evidence(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir(parents=True)
    (runtime / "system_scorecard.json").write_text(
        '{"ai_capability_score":{"score":37,"max_score":100},'
        '"efficiency_score":{"score":61,"max_score":100,"capability_per_compute":0.42,"samples":4},'
        '"immortality_research_progress_score":{"score":55,"max_score":100,'
        '"interpretation":"Evidence-pipeline maturity; not percent immortality achieved."}}',
        encoding="utf-8",
    )
    queue = PersistentTaskQueue(runtime / "genesis_tasks.sqlite3")
    queue.create_unique("email-test", "Test task", module_id="genesis.email_reporter", priority=1)

    reporter = GenesisEmailReporter(tmp_path)
    snapshot = reporter.snapshot()
    assert snapshot["ai_score"] == "37/100"
    assert snapshot["efficiency_score"] == "61/100"
    assert snapshot["efficiency_samples"] == 4
    assert snapshot["open_tasks"] == 1

    subject, text, body = reporter.render(snapshot)
    assert subject.startswith("Genesis Hourly Update")
    assert "GENESIS AI — HOURLY KPI DASHBOARD" in text
    assert "Generated and sent directly by Genesis runtime automation" in body


def test_email_reporter_does_not_invent_missing_scores(tmp_path: Path) -> None:
    reporter = GenesisEmailReporter(tmp_path)
    snapshot = reporter.snapshot()
    assert snapshot["ai_score"] == "Unmeasured"
    assert snapshot["efficiency_score"] == "Unmeasured"
    assert snapshot["research_score"] == "Unmeasured"
