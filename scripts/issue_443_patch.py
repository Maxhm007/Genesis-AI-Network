from pathlib import Path

router = Path("genesis/task_router.py")
text = router.read_text(encoding="utf-8")
old = '''    (("model", "provider", "inference", "reasoning", "benchmark model"), "genesis.model_scout"),\n'''
new = '''    ((\n        "model",\n        "provider",\n        "inference",\n        "reasoning",\n        "benchmark model",\n        "speculative decoding",\n        "decode context parallel",\n        "decode-context parallel",\n        "moe",\n        "rocm",\n        "cuda graph",\n        "tensor parallel",\n    ), "genesis.model_scout"),\n'''
if text.count(old) != 1:
    raise SystemExit("model routing rule anchor mismatch")
router.write_text(text.replace(old, new, 1), encoding="utf-8")


tests = Path("tests/test_task_router_model_scout.py")
test_text = tests.read_text(encoding="utf-8")
append = '''\n\ndef test_vllm_runtime_release_signals_route_to_model_scout(tmp_path: Path):\n    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")\n    for objective in (\n        "Tune speculative decoding confidence scheduling",\n        "Enable decode context parallel execution",\n        "Validate ROCm sparse MLA runtime",\n        "Narrow eager CUDA graph regions",\n        "Plan MoE tensor parallel execution",\n    ):\n        task = queue.create(objective)\n        decision = TaskRouterModule.route(task)\n        assert decision.module_id == "genesis.model_scout"\n'''
if "test_vllm_runtime_release_signals_route_to_model_scout" not in test_text:
    tests.write_text(test_text.rstrip() + append + "\n", encoding="utf-8")
