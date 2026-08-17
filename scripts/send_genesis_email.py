from __future__ import annotations

import json
from pathlib import Path

from genesis.email_reporter import EmailDeliveryConfig, GenesisEmailReporter


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    reporter = GenesisEmailReporter(ROOT)
    config = EmailDeliveryConfig.from_env()
    result = reporter.send(config)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
