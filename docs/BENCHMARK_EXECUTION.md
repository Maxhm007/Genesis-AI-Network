# Autonomous benchmark execution

Genesis treats an unmeasured frontier benchmark as an evaluation problem, not as permission to edit its score.

Flow:

1. `CompetitiveBenchmarkPlanner` creates a durable `genesis.evaluation` task.
2. `scripts/benchmark_task_worker.py` advances one evaluation task per bounded cycle.
3. `BenchmarkExecutionPlanner` stages real benchmark output only through a benchmark-specific evidence adapter.
4. When a real result is not yet available, it creates one deduplicated `genesis.coding` task to implement/configure the missing official/comparable runner.
5. The evaluation task pauses while runner work proceeds instead of consuming repeated repair attempts.
6. Staged evidence cannot change the competitive score until independent validation promotes it.

Hard rule: benchmark scores may never be invented, estimated from model identity, hard-coded, or inferred from architecture.
