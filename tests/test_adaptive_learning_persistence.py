from pathlib import Path

from genesis.adaptive_learning import AdaptiveLearningEngine


def test_adaptive_outcomes_use_persistent_self_learning_database(tmp_path: Path):
    engine = AdaptiveLearningEngine(tmp_path)
    assert engine.store.path == tmp_path / "runtime" / "self_learning.sqlite3"
