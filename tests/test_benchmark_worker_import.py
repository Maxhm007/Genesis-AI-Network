def test_benchmark_worker_imports():
    import scripts.benchmark_task_worker as worker
    assert callable(worker.main)
