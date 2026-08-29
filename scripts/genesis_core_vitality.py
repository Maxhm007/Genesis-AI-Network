replacement text
import json

from genesis.core_vitality import CoreVitalityMonitor


if __name__ == "__main__":
    report = CoreVitalityMonitor(Path(".")).evaluate()
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["operational"] else 2)
