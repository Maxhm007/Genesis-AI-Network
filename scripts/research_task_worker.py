from pathlib import Path
import json

from genesis.research_tasks import ImmortalityResearchWorker
from genesis.self_improvement_backlog_drain import route_existing_self_improvement


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    adoption = route_existing_self_improvement(root)
    result = ImmortalityResearchWorker(root).run_one()
    print(json.dumps({"self_improvement_adoption": adoption, "worker": result}, indent=2))


if __name__ == "__main__":
    main()
