from __future__ import annotations

import json
from pathlib import Path

from genesis.memory import GenesisMemory
from genesis.self_learning import SelfLearningStore


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    memory = GenesisMemory(ROOT)
    learning = SelfLearningStore(ROOT / "runtime" / "self_learning.sqlite3")
    imported = 0
    for lesson in learning.list(state="validated", limit=1000):
        before = memory.store.stats()["total"]
        memory.remember_validated_lesson(lesson)
        if memory.store.stats()["total"] > before:
            imported += 1
    status = memory.write_status(ROOT / "runtime" / "memory_status.json")
    print(json.dumps({"imported": imported, **status}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
