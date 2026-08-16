from pathlib import Path
import json

from genesis.competitive_reference import CompetitiveReferenceMonitor


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    result = CompetitiveReferenceMonitor(root).check()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
