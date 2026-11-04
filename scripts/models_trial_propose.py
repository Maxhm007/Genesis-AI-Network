"""Ask Genesis's own CodingModule (backed by a localhost provider) for a #843 fix.

Writes the fix as a patch file. Only genesis/memory.py may change; nothing is committed or pushed.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from genesis.coding import CodingModule  # noqa: E402
from genesis.selfdev import normalize_selfdev_path  # noqa: E402

TARGET = "genesis/memory.py"
TEST = ".github/trials/843/test_memory_metadata_validation.py"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue-json", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--attempts", type=int, default=3)
    args = parser.parse_args()
    issue = json.loads(Path(args.issue_json).read_text(encoding="utf-8"))
    body = str(issue.get("body") or "").split("### Genesis FIFO")[0]
    objective = (
        str(issue.get("title") or "") + "\n\n" + body
        + "\nThe fix must make this regression test pass without breaking valid JSON-safe metadata:\n"
        + (ROOT / TEST).read_text(encoding="utf-8")
    )
    report = []
    for attempt in range(1, max(1, min(args.attempts, 5)) + 1):
        subprocess.run(["git", "checkout", "-q", "--", TARGET], cwd=ROOT, check=True)
        entry: dict = {"attempt": attempt}
        try:
            proposal = CodingModule(ROOT).propose(objective, [TARGET])
            paths = sorted(proposal.files)
            entry["files"] = paths
            if [normalize_selfdev_path(ROOT, p) for p in paths] != [TARGET]:
                raise ValueError(f"proposal touches files other than {TARGET}")
            (ROOT / TARGET).write_text(proposal.files[TARGET], encoding="utf-8")
            diff = subprocess.run(["git", "diff", "--", TARGET], cwd=ROOT, capture_output=True, text=True, check=True).stdout
            if not diff.strip():
                raise ValueError("proposal produced no change")
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", TEST, "tests/test_memory.py"],
                cwd=ROOT, capture_output=True, text=True,
            )
            entry["tests"] = (result.stdout.strip().splitlines() or [""])[-1][:200]
            entry["passed"] = result.returncode == 0
            if entry["passed"]:
                Path(args.out).write_text(diff, encoding="utf-8")
        except Exception as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"[:400]
        report.append(entry)
        print(json.dumps(entry), flush=True)
        if entry.get("passed"):
            break
    subprocess.run(["git", "checkout", "-q", "--", TARGET], cwd=ROOT)
    Path(args.out + ".json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
