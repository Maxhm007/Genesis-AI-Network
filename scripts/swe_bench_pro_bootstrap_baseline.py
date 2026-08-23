from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from datasets import load_dataset

from genesis.providers import ProviderRegistry
from genesis.swe_bench_pro_evidence import (
    BASELINE_MODE,
    SWE_BENCH_PRO_DATASET,
    SWE_BENCH_PRO_REVISION,
    SWE_BENCH_PRO_TASK_COUNT,
    SWEBenchProEvidenceAdapter,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    registry = ProviderRegistry(root=root)
    available = sorted(status.name for status in registry.statuses() if status.available)
    non_bootstrap = [name for name in available if name != "genesis-bootstrap"]
    if non_bootstrap:
        raise SystemExit(
            "Providerless SWE-bench Pro baseline refused because non-bootstrap providers are available: "
            + ", ".join(non_bootstrap)
        )
    if available != ["genesis-bootstrap"]:
        raise SystemExit(
            "Providerless SWE-bench Pro baseline requires genesis-bootstrap as the sole available provider; "
            f"observed={available!r}"
        )

    dataset = load_dataset(
        SWE_BENCH_PRO_DATASET,
        split="test",
        revision=SWE_BENCH_PRO_REVISION,
    )
    rows = [dict(row) for row in dataset]
    if len(rows) != SWE_BENCH_PRO_TASK_COUNT:
        raise SystemExit(
            f"Pinned SWE-bench Pro revision returned {len(rows)} tasks; expected {SWE_BENCH_PRO_TASK_COUNT}"
        )

    adapter = SWEBenchProEvidenceAdapter(root)
    results = []
    for row in rows:
        identity = adapter.dataset_identity(row)
        results.append(
            {
                "instance_id": identity["instance_id"],
                "patch": "",
                "outcome": "no_patch",
                "dataset_identity": identity,
                "record_sha256": adapter._canonical_hash(identity),
            }
        )
    results.sort(key=lambda item: item["instance_id"])
    task_set_sha256 = adapter._canonical_hash(results)

    measured_at = utc_now()
    source_url = (
        f"https://huggingface.co/datasets/{SWE_BENCH_PRO_DATASET}/tree/{SWE_BENCH_PRO_REVISION}"
    )
    job = {
        "dataset": SWE_BENCH_PRO_DATASET,
        "revision": SWE_BENCH_PRO_REVISION,
        "mode": BASELINE_MODE,
        "measured_at": measured_at,
        "source_url": source_url,
        "available_providers": available,
        "provider_discovery_errors": list(registry.discovery_errors()),
        "task_count": len(results),
        "task_set_sha256": task_set_sha256,
        "measurement_basis": (
            "Genesis had no available non-bootstrap coding provider on the measurement runner. "
            "Its providerless coding mode therefore emitted no patch for every pinned public task. "
            "The SWE-bench Pro evaluator treats a missing/empty applicable patch as an unresolved task; "
            "the adapter derives zero credit and never accepts a caller-supplied score."
        ),
        "results": results,
    }

    input_dir = root / "runtime" / "competitive_benchmark_inputs"
    input_dir.mkdir(parents=True, exist_ok=True)
    input_path = input_dir / "swe_bench_pro.json"
    input_path.write_text(json.dumps(job, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    candidate_path = adapter.stage(job)
    print(
        json.dumps(
            {
                "status": "candidate_staged",
                "benchmark_id": "swe_bench_pro",
                "score": 0.0,
                "mode": BASELINE_MODE,
                "task_count": len(results),
                "input_path": str(input_path.relative_to(root)),
                "candidate_path": str(candidate_path.relative_to(root)),
                "available_providers": available,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
