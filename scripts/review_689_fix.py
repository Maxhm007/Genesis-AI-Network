from pathlib import Path

capabilities = Path("genesis/learned_capabilities.py")
text = capabilities.read_text(encoding="utf-8")

old = '''    divergence = sum(values)\n    return {\n        "steps": len(values),\n        "conditional_divergence": divergence,\n        "peeking_penalty": penalty,\n        "information_budget": divergence + penalty,\n    }\n'''
new = '''    divergence = sum(values)\n    budget = divergence + penalty\n    if divergence == float("inf") or budget == float("inf"):\n        raise ValueError("information budget exceeds finite bounds")\n    return {\n        "steps": len(values),\n        "conditional_divergence": divergence,\n        "peeking_penalty": penalty,\n        "information_budget": budget,\n    }\n'''
if text.count(old) != 1:
    raise SystemExit("martingale review insertion point mismatch")
text = text.replace(old, new, 1)

old = '''    total = sum(weights)\n    if total <= 0.0:\n        raise ValueError("tensor split requires positive total device weight")\n'''
new = '''    total = sum(weights)\n    if total <= 0.0 or total == float("inf"):\n        raise ValueError("tensor split requires positive finite total device weight")\n'''
if text.count(old) != 1:
    raise SystemExit("tensor split review insertion point mismatch")
text = text.replace(old, new, 1)

old = '''    choices = tuple(str(item).strip() for item in available if str(item).strip())\n    for candidate in (explicit_device, legacy_device, default):\n'''
new = '''    choices_list: list[str] = []\n    for index, item in enumerate(available):\n        if index >= 64:\n            raise ValueError("available device scan exceeds bound")\n        name = str(item).strip()\n        if name:\n            choices_list.append(name)\n    choices = tuple(choices_list)\n    for candidate in (explicit_device, legacy_device, default):\n'''
# Only replace the #433 instance, which is the last matching device-selection helper in the file.
position = text.rfind(old)
if position < 0:
    raise SystemExit("mmproj review insertion point not found")
text = text[:position] + text[position:].replace(old, new, 1)
capabilities.write_text(text, encoding="utf-8")


tests = Path("tests/test_learned_capabilities_issue_cluster.py")
test_text = tests.read_text(encoding="utf-8")
append = '''\n\ndef test_issue_427_rejects_aggregate_float_overflow():\n    with pytest.raises(ValueError, match="finite bounds"):\n        run_capability("martingale_information_budget_427", [1e308, 1e308])\n\n\ndef test_issue_431_rejects_weight_sum_overflow():\n    with pytest.raises(ValueError, match="positive finite"):\n        run_capability("lfm2_tensor_split_plan_431", "LFM2", [1e308, 1e308])\n\n\ndef test_issue_433_bounds_available_device_scan():\n    with pytest.raises(ValueError, match="scan exceeds bound"):\n        run_capability("mmproj_device_selection_433", None, None, ["cpu"] * 65)\n'''
if "test_issue_427_rejects_aggregate_float_overflow" not in test_text:
    tests.write_text(test_text.rstrip() + append + "\n", encoding="utf-8")
