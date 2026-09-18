import json
from pathlib import Path

import pytest

from genesis.benchmark_evidence import BenchmarkEvidenceError
from genesis.coding_agent_index_evidence import COMPONENTS, CodingAgentIndexEvidenceAdapter


def make_component(component_id: str, passed_attempts: int = 0) -> dict:
    count = COMPONENTS[component_id]["task_count"]
    total = count * 3
    bits = [True] * passed_attempts + [False] * (total - passed_attempts)
    tasks = [
        {"task_id": f"{component_id}-{index}", "attempts": bits[index * 3:(index + 1) * 3]}
        for index in range(count)
    ]
    return {
        "benchmark_id": component_id,
        "task_count": count,
        "attempts_per_task": 3,
        "dataset": component_id,
        "dataset_revision": "pinned-test-revision",
        "runner_name": "official-compatible",
        "runner_version": "1",
        "runner_config": "test",
        "source_url": "https://example.com/result",
        "tasks": tasks,
    }


def make_job() -> dict:
    return {
        "index_version": "1.5",
        "source_url": "https://artificialanalysis.ai/methodology/coding-agents-benchmarking",
        "measured_at": "2026-09-18T00:00:00Z",
        "agent": "Genesis",
        "model": "test-model",
        "harness": "test-harness",
        "components": {
            "deep_swe_v1_1": make_component("deep_swe_v1_1", 113 * 3),
            "terminal_bench_4_0": make_component("terminal_bench_4_0", 0),
            "swe_atlas_qna": make_component("swe_atlas_qna", 124 * 3 // 2),
        },
    }


def write_reference(root: Path) -> None:
    (root / "config").mkdir()
    (root / "config" / "competitive_ai_reference.json").write_text(
        json.dumps({"benchmarks": [{"id": "coding_agent_index", "family": "coding_agents", "unit": "index"}]}),
        encoding="utf-8",
    )


def test_builds_index_only_from_task_level_attempts(tmp_path: Path) -> None:
    write_reference(tmp_path)
    evidence = CodingAgentIndexEvidenceAdapter(tmp_path).build_evidence(make_job())
    expected = (100.0 + 0.0 + (100.0 * (124 * 3 // 2) / (124 * 3))) / 3
    assert evidence["score"] == pytest.approx(expected)
    assert evidence["raw_result"]["computed_index"] == pytest.approx(expected)
    assert evidence["runner"]["version"] == "1.5"


def test_rejects_incomplete_component_task_set(tmp_path: Path) -> None:
    job = make_job()
    job["components"]["deep_swe_v1_1"]["tasks"].pop()
    with pytest.raises(BenchmarkEvidenceError, match="requires exactly 113 task results"):
        CodingAgentIndexEvidenceAdapter(tmp_path).build_evidence(job)


def test_rejects_non_three_attempts(tmp_path: Path) -> None:
    job = make_job()
    job["components"]["terminal_bench_4_0"]["tasks"][0]["attempts"] = [True]
    with pytest.raises(BenchmarkEvidenceError, match="exactly three attempts"):
        CodingAgentIndexEvidenceAdapter(tmp_path).build_evidence(job)


def test_stage_and_independently_rebuild_candidate(tmp_path: Path) -> None:
    write_reference(tmp_path)
    adapter = CodingAgentIndexEvidenceAdapter(tmp_path)
    path = adapter.stage(make_job())
    candidate = json.loads(path.read_text(encoding="utf-8"))
    assert adapter.validate_staged_candidate(candidate) == candidate


def test_tampered_score_fails_independent_rebuild(tmp_path: Path) -> None:
    write_reference(tmp_path)
    adapter = CodingAgentIndexEvidenceAdapter(tmp_path)
    path = adapter.stage(make_job())
    candidate = json.loads(path.read_text(encoding="utf-8"))
    candidate["score"] += 1
    with pytest.raises(BenchmarkEvidenceError, match="does not match"):
        adapter.validate_staged_candidate(candidate)
