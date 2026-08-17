from __future__ import annotations

import json
from pathlib import Path

from genesis.task_router import TaskRouterModule


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    router = TaskRouterModule(root)
    print(json.dumps(router.assign_next(), indent=2, sort_keys=True))
