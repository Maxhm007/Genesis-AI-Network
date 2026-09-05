from pathlib import Path

path = Path("genesis/learned_capabilities.py")
text = path.read_text(encoding="utf-8")
old = '''    values = tuple(float(item) for item in step_divergences)\n    if len(values) > 4096 or any(item < 0.0 or item != item or item == float("inf") for item in values):\n        raise ValueError("step divergences must be finite, non-negative, and bounded")\n'''
new = '''    values_list: list[float] = []\n    for index, item in enumerate(step_divergences):\n        if index >= 4096:\n            raise ValueError("step divergences exceed bounded input size")\n        value = float(item)\n        if value < 0.0 or value != value or value == float("inf"):\n            raise ValueError("step divergences must be finite, non-negative, and bounded")\n        values_list.append(value)\n    values = tuple(values_list)\n'''
if text.count(old) != 1:
    raise SystemExit("divergence iterator anchor mismatch")
text = text.replace(old, new, 1)
old = '''    weights = tuple(float(item) for item in device_weights)\n    if not weights or len(weights) > 32 or any(item < 0.0 or item != item or item == float("inf") for item in weights):\n        raise ValueError("device weights must be finite, non-negative, and bounded")\n'''
new = '''    weights_list: list[float] = []\n    for index, item in enumerate(device_weights):\n        if index >= 32:\n            raise ValueError("device weights exceed bounded input size")\n        value = float(item)\n        if value < 0.0 or value != value or value == float("inf"):\n            raise ValueError("device weights must be finite, non-negative, and bounded")\n        weights_list.append(value)\n    weights = tuple(weights_list)\n    if not weights:\n        raise ValueError("device weights must be finite, non-negative, and bounded")\n'''
if text.count(old) != 1:
    raise SystemExit("weight iterator anchor mismatch")
path.write_text(text.replace(old, new, 1), encoding="utf-8")


tests = Path("tests/test_learned_capabilities_issue_cluster.py")
test_text = tests.read_text(encoding="utf-8")
append = '''\n\ndef test_issue_427_bounds_iterator_consumption():\n    def values():\n        while True:\n            yield 0.01\n    with pytest.raises(ValueError, match="bounded input size"):\n        run_capability("martingale_information_budget_427", values())\n\n\ndef test_issue_431_bounds_weight_iterator_consumption():\n    def weights():\n        while True:\n            yield 1.0\n    with pytest.raises(ValueError, match="bounded input size"):\n        run_capability("lfm2_tensor_split_plan_431", "LFM2", weights())\n'''
if "test_issue_427_bounds_iterator_consumption" not in test_text:
    tests.write_text(test_text.rstrip() + append + "\n", encoding="utf-8")
