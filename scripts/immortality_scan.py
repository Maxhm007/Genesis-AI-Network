from __future__ import annotations

import json
from pathlib import Path

from genesis.ai_score import GenesisAIScorer
from genesis.immortality_scan import ImmortalityScanner


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    scan = ImmortalityScanner(root).scan()
    scorer = GenesisAIScorer(root)
    history = scorer.append_history(root / "runtime" / "ai_score_history.jsonl")
    summary = {
        "scan_created_at": scan["created_at"],
        "sources_checked": scan["sources_checked"],
        "scan_errors": scan["errors"],
        "priority_count": len(scan["priority_items"]),
        "persistent_tasks": scan.get("persistent_tasks", {}),
        "top_priority_items": scan["priority_items"][:5],
        "competitive_ai_score": history,
    }
    (root / "runtime" / "ai_score.json").write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
