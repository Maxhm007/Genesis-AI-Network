from __future__ import annotations

import json
from pathlib import Path

from genesis.selfdev import SelfDevelopmentExecutor


def main() -> None:
    root = Path(__file__).resolve().parent
    result = SelfDevelopmentExecutor(root).execute()
    print(json.dumps({
        "branch": result.branch,
        "candidate_id": result.candidate_id,
        "tests_passed": result.tests_passed,
        "committed": result.committed,
        "changed_files": list(result.changed_files),
        "commit_sha": result.commit_sha,
        "message": result.message,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
