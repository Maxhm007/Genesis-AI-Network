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


def run(root: Path = ROOT, *, repository: str | None = None, provider=None) -> dict:
    """Publish at most one fresh grounded issue without candidate starvation.

    Discovery keeps moving through eligible ranked candidates until it either
    opens one fresh Issue or exhausts the complete eligible candidate set for
    the current repository snapshot. Duplicate findings, provider timeouts, and
    clean batches are excluded only for the remainder of this invocation.
    Strict validation and all-state deduplication remain unchanged.
    """

    root = Path(root).resolve()
    runtime = root / "runtime" / "github_issue_discovery"
    runtime.mkdir(parents=True, exist_ok=True)
    queue = PersistentTaskQueue(runtime / "tasks.sqlite3")
    provider = provider or CodingModule(root)._provider()
    engine = GenesisIssueDiscoveryEngine(root)
    repository = repository or os.environ.get("GITHUB_REPOSITORY", "").strip()

    original_rank_candidates = engine.rank_candidates
    eligible_candidates = original_rank_candidates(include_protected=False)
    eligible_targets = {candidate.path for candidate in eligible_candidates}
    excluded_targets: set[str] = set()
    duplicate_publications: list[dict] = []
    timeout_skips: list[dict] = []
    clean_batch_skips: list[str] = []
    last_discovery: dict | None = None

    while eligible_targets - excluded_targets:
        def rank_without_blockers(*, include_protected: bool = False):
            return [
                candidate
                for candidate in original_rank_candidates(include_protected=include_protected)
                if candidate.path not in excluded_targets
            ]

        engine.rank_candidates = rank_without_blockers  # type: ignore[method-assign]
        discovery_result = engine.discover_and_enqueue(queue, provider)
        last_discovery = discovery_result

        result: dict = {
            "status": "discovery_complete",
            "discovery": discovery_result,
            "publication": {"status": "not_publishable"},
            "eligible_candidate_count": len(eligible_targets),
            "scanned_or_excluded_count": len(excluded_targets),
            "skipped_duplicate_publications": duplicate_publications,
            "skipped_provider_timeouts": timeout_skips,
            "skipped_clean_targets": clean_batch_skips,
        }

        discovery_status = str(discovery_result.get("status") or "")
        if discovery_status not in ELIGIBLE_DISCOVERY_STATUSES:
            timed_out_targets: list[str] = []
            scanned_targets: list[str] = []
            for scan in discovery_result.get("scanned") or []:
                if not isinstance(scan, dict):
                    continue
                target = str(scan.get("target") or "").strip()
                if target and target in eligible_targets and target not in excluded_targets:
                    scanned_targets.append(target)

                if scan.get("status") != "provider_error":
                    continue
                error = str(scan.get("error") or "").lower()
                if "timeout" not in error and "timed out" not in error:
                    continue
                if target and target in eligible_targets and target not in excluded_targets:
                    timed_out_targets.append(target)
                    timeout_skips.append({
                        "target": target,
                        "error": str(scan.get("error") or "")[:1000],
                    })

            if timed_out_targets:
                excluded_targets.update(timed_out_targets)
                continue

            # A clean batch is not evidence that the repository has no work.
            # Exclude every target inspected in this invocation and continue to
            # the next ranked candidates until the complete eligible set is done.
            if discovery_status == "no_issue_found" and scanned_targets:
                fresh_scanned_targets = [
                    target for target in scanned_targets if target not in excluded_targets
                ]
                if fresh_scanned_targets:
                    excluded_targets.update(fresh_scanned_targets)
                    clean_batch_skips.extend(fresh_scanned_targets)
                    continue

            # No progress means there is no safe candidate left to advance.
            result["status"] = discovery_status or "no_issue_found"
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
        "status": "candidates_exhausted",
        "discovery": last_discovery or {"status": "no_issue_found"},
        "publication": {"status": "no_fresh_issue_after_full_scan"},
        "eligible_candidate_count": len(eligible_targets),
        "scanned_or_excluded_count": len(excluded_targets),
        "skipped_duplicate_publications": duplicate_publications,
        "skipped_provider_timeouts": timeout_skips,
        "skipped_clean_targets": clean_batch_skips,
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
