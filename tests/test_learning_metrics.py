import json
import sqlite3

from genesis.learning_metrics import learning_metrics


def test_metrics_missing_database_never_invents_success(tmp_path):
    result = learning_metrics(tmp_path / "missing.sqlite3")
    assert result["status"] == "no_evidence"
    assert result["promotion_rate"] is None


def test_metrics_count_verified_lifecycle_and_failure_evidence(tmp_path):
    db = tmp_path / "learning.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.executescript("""
            CREATE TABLE research_items(status TEXT);
            CREATE TABLE upgrade_opportunities(state TEXT);
            CREATE TABLE upgrade_events(event_id INTEGER PRIMARY KEY, status TEXT, message TEXT, details_json TEXT);
            INSERT INTO research_items VALUES ('pending'), ('evaluated'), ('enqueued');
            INSERT INTO upgrade_opportunities VALUES ('promoted'), ('repair_ready'), ('closed');
        """)
        conn.execute("INSERT INTO upgrade_events(status,message,details_json) VALUES(?,?,?)",
                     ("failed", "Provider timed out", json.dumps({"reason": "timeout"})))
    result = learning_metrics(db)
    assert result["research_total"] == 3
    assert result["opportunity_total"] == 3
    assert result["promoted_total"] == 2
    assert result["promotion_rate"] == 0.6667
    assert result["recent_failure_reasons"][0]["reason"] == "timeout"


def test_metrics_empty_database_has_no_rate(tmp_path):
    db = tmp_path / "empty.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.executescript("""
            CREATE TABLE research_items(status TEXT);
            CREATE TABLE upgrade_opportunities(state TEXT);
            CREATE TABLE upgrade_events(event_id INTEGER PRIMARY KEY, status TEXT, message TEXT, details_json TEXT);
        """)
    assert learning_metrics(db)["promotion_rate"] is None
