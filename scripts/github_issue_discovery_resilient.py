from __future__ import annotations

import json
import os
from pathlib import Path

from genesis.coding import CodingModule
from genesis.issue_discovery import GenesisIssueDiscoveryEngine
from genesis.modules.task_queue import PersistentTaskQueue
from scripts.github_issue_discovery import (
    ELIGIBLE_DISCOVERY_STATUSES,
    EVIDENCE_PATH,
    publish_discovery,
    validate_discovery,
)


ROOT = Path(__file__).resolve().parents[1]
MAX_DISCOVERY_PASSES = 6


def run(root: Path = ROOT, *, repository: str | None = None, provider=None) -> dict:
    """Publish at most one fresh grounded issue without duplicate starvation.

    A discovery pass can repeatedly find the same valid problem for a source
    version that already has a GitHub Issue (including a closed Issue). The
    original runner stopped at that duplicate, so one high-ranked finding could
    starve every lower-ranked candidate forever. This runner keeps the strict
    validation and all-state deduplication boundary, but excludes a duplicate
    target for the remainder of the current run and continues discovery.
    """

    root = Path(root).resolve()
    runtime = root / "runtime" / "github_issue_discovery"
    runtime.mkdir(parents=True, exist_ok=True)
    queue = PersistentTaskQueue(runtime / "tasks.sqlite3")
    provider = provider or CodingModule(root)._provider()
    engine = GenesisIssueDiscoveryEngine(root)
    repository = repository or os.environ.get("GITHUB_REPOSITORY", "").strip()

    original_rank_candidates = engine.rank_candidates
    excluded_targets: set[str] = set()
    duplicate_publications: list[dict] = []
    last_discovery: dict | None = None

    for _ in range(MAX_DISCOVERY_PASSES):
        def rank_without_duplicates(*, include_protected: bool = False):
            return [
                candidate
                for candidate in original_rank_candidates(include_protected=include_protected)
                if candidate.path not in excluded_targets
            ]

        engine.rank_candidates = rank_without_duplicates  # type: ignore[method-assign]
        discovery_result = engine.discover_and_enqueue(queue, provider)
        last_discovery = discovery_result

        result: dict = {
            "status": "discovery_complete",
            "discovery": discovery_result,
            "publication": {"status": "not_publishable"},
            "skipped_duplicate_publications": duplicate_publications,
        }

        if str(discovery_result.get("status") or "") not in ELIGIBLE_DISCOVERY_STATUSES:
            result["status"] = str(discovery_result.get("status") or "no_issue_found")
            EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
            EVIDENCE_PATH.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return result

        validated = validate_discovery(discovery_result, root)
        if not repository:
            raise RuntimeError("GITHUB_REPOSITORY is required to publish a discovered issue")

        publication = publish_discovery(validated, repository=repository)
        result["validated_discovery"] = validated
        result["publication"] = publication

        if publication["status"] == "issue_opened":
            result["status"] = "issue_opened"
            EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
            EVIDENCE_PATH.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return result

        if publication["status"] != "duplicate_existing_issue":
            result["status"] = str(publication.get("status") or "publication_stopped")
            EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
            EVIDENCE_PATH.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return result

        duplicate_publications.append(
            {
                "target": validated["target"],
                "source_sha": validated["source_sha"],
                **publication,
            }
        )
        excluded_targets.add(validated["target"])

    result = {
        "status": "duplicates_exhausted",
        "discovery": last_discovery or {"status": "no_issue_found"},
        "publication": {"status": "no_fresh_issue_after_duplicate_scan"},
        "skipped_duplicate_publications": duplicate_publications,
    }
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    try:
        result = run(ROOT)
    except Exception as exc:
        result = {"status": "error", "error": f"{type(exc).__name__}: {exc}"[:2000]}
        EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE_PATH.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2, sort_keys=True))
        raise SystemExit(1) from exc
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
