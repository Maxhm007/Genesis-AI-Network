from pathlib import Path

from genesis.modules.benchmarking import BenchmarkEngine


def test_benchmark_engine_compares_before_and_after(tmp_path: Path):
    engine = BenchmarkEngine(tmp_path)
    engine.register("repair-seeded", "genesis.repair", lambda: (7, 10, {"fixed": 7, "total": 10}))
    before = engine.run("repair-seeded")
    assert before.percent == 70.0

    improved = BenchmarkEngine(tmp_path)
    improved.register("repair-seeded", "genesis.repair", lambda: (9, 10, {"fixed": 9, "total": 10}))
    after = improved.run("repair-seeded")
    comparison = BenchmarkEngine.compare(before, after)
    assert comparison["improved"] is True
    assert comparison["delta_percent"] == 20.0


def test_benchmark_rejects_invalid_score(tmp_path: Path):
    engine = BenchmarkEngine(tmp_path)
    engine.register("bad", "genesis.repair", lambda: (11, 10, {}))
    try:
        engine.run("bad")
        assert False, "expected ValueError"
    except ValueError:
        pass
