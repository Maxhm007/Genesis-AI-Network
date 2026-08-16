from __future__ import annotations

import json
from pathlib import Path

from genesis.self_learning import SelfLearningEngine


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    result = SelfLearningEngine(root).run_once()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
