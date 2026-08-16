from pathlib import Path
import json

from genesis.research_tasks import ImmortalityResearchWorker


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    result = ImmortalityResearchWorker(root).run_one()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
