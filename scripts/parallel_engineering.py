from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

from genesis.efficient_engineering import EfficientAutonomousEngineeringLoop
from genesis.parallel_engineering import ParallelDevelopmentPlanner, reconcile_parallel_results


def root() -> Path:
    return Path(__file__).resolve().parents[1]


def _write_output(name: str, value: str) -> None:
    target = os.environ.get("GITHUB_OUTPUT")
    if not target:
        return
    with open(target, "a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def cmd_plan() -> int:
    report = ParallelDevelopmentPlanner(root()).plan()
    matrix = {"include": report["tasks"]}
    _write_output("has_tasks", "true" if report["tasks"] else "false")
    _write_output("matrix", json.dumps(matrix, separators=(",", ":")))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def cmd_worker(task_id: str) -> int:
    result = EfficientAutonomousEngineeringLoop(root()).run_selected(task_id)
    candidate = result.get("candidate") or {}
    branch = str(candidate.get("branch") or "")
    sha = str(candidate.get("commit_sha") or "")
    has_candidate = bool(result.get("coding_status") == "candidate_created" and branch and sha)
    result["parallel_rank"] = int(os.environ.get("GENESIS_PARALLEL_RANK", "999"))
    result["has_candidate"] = has_candidate
    result["candidate_branch"] = branch
    result["candidate_sha"] = sha
    path = root() / "runtime" / f"parallel_result_{task_id}.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_output("has_candidate", "true" if has_candidate else "false")
    _write_output("candidate_branch", branch)
    _write_output("candidate_sha", sha)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _load_jsons(directory: Path, pattern: str) -> list[dict]:
    rows: list[dict] = []
    if not directory.exists():
        return rows
    for path in sorted(directory.rglob(pattern)):
        try:
            rows.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    return rows


def cmd_select(artifacts: Path) -> int:
    results = _load_jsons(artifacts, "parallel_result_*.json")
    votes_a = {p.stem.removeprefix("validator_a_"): p for p in artifacts.rglob("validator_a_*.json")}
    votes_b = {p.stem.removeprefix("validator_b_"): p for p in artifacts.rglob("validator_b_*.json")}
    eligible = []
    for result in results:
        task = result.get("selected_task") or {}
        task_id = str(task.get("task_id") or "")
        if not result.get("has_candidate") or task_id not in votes_a or task_id not in votes_b:
            continue
        rank = int(result.get("parallel_rank", 999) or 999)
        eligible.append((rank, task_id, result, votes_a[task_id], votes_b[task_id]))
    eligible.sort(key=lambda row: (row[0], row[1]))
    selection = {}
    runtime = root() / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    if eligible:
        _, task_id, result, vote_a, vote_b = eligible[0]
        chosen_a = runtime / "selected_validator_a.json"
        chosen_b = runtime / "selected_validator_b.json"
        shutil.copyfile(vote_a, chosen_a)
        shutil.copyfile(vote_b, chosen_b)
        selection = {
            "task_id": task_id,
            "candidate_branch": result.get("candidate_branch"),
            "candidate_sha": result.get("candidate_sha"),
            "validator_a": str(chosen_a),
            "validator_b": str(chosen_b),
        }
    path = runtime / "parallel_promotion.json"
    path.write_text(json.dumps(selection, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_output("has_candidate", "true" if selection else "false")
    _write_output("task_id", str(selection.get("task_id") or ""))
    _write_output("candidate_branch", str(selection.get("candidate_branch") or ""))
    _write_output("candidate_sha", str(selection.get("candidate_sha") or ""))
    print(json.dumps(selection, indent=2, sort_keys=True))
    return 0


def cmd_reconcile(artifacts: Path) -> int:
    results = _load_jsons(artifacts, "parallel_result_*.json")
    promotion_path = root() / "runtime" / "parallel_promotion.json"
    promotion = json.loads(promotion_path.read_text(encoding="utf-8")) if promotion_path.is_file() else {}
    report = reconcile_parallel_results(root(), results, promotion)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan")
    worker = sub.add_parser("worker")
    worker.add_argument("--task-id", required=True)
    select = sub.add_parser("select")
    select.add_argument("--artifacts", type=Path, required=True)
    reconcile = sub.add_parser("reconcile")
    reconcile.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "plan":
        return cmd_plan()
    if args.command == "worker":
        return cmd_worker(args.task_id)
    if args.command == "select":
        return cmd_select(args.artifacts)
    return cmd_reconcile(args.artifacts)


if __name__ == "__main__":
    raise SystemExit(main())
