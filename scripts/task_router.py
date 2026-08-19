from __future__ import annotations

import json
from pathlib import Path

from genesis.core_processor import GenesisCoreProcessor


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    processor = GenesisCoreProcessor(root)
    print(json.dumps(processor.cycle(), indent=2, sort_keys=True))
