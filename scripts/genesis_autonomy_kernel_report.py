from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone

from genesis.autonomy_kernel import summarize_issues


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False)


def _issues(repository: str) -> list[dict]:
    result = _run(["gh", "api", f"repos/{repository}/issues?state=all&per_page=100"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-1200:])
    rows = json.loads(result.stdout or "[]")
    return [row for row in rows if isinstance(row, dict) and not row.get("pull_request")]


def build_report(repository: str) -> dict:
    report = summarize_issues(_issues(repository), now=datetime.now(timezone.utc))
    report["repository"] = repository
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    return report


def _write_summary(report: dict) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
    if not path:
        return
    counts = report["state_counts"]
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("# Genesis Autonomy Kernel v2\n\n")
        handle.write(f"- Autonomous open issues: **{report['autonomous_open_count']}**\n")
        handle.write(f"- Human intervention required: **{report['human_intervention_required_count']}**\n")
        handle.write(f"- Unattended-open ratio: **{report['unattended_open_ratio']:.0%}**\n")
        handle.write(f"- Ready: **{counts.get('ready', 0)}**\n")
        handle.write(f"- Working: **{counts.get('working', 0)}**\n")
        handle.write(f"- Validating: **{counts.get('validating', 0)}**\n")
        handle.write(f"- Blocked: **{counts.get('blocked', 0)}**\n")
        handle.write(f"- Recovery queue: **{report['recovery_issue_numbers']}**\n")
        handle.write(f"- Verified to close: **{report['verified_to_close_issue_numbers']}**\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a machine-verifiable Genesis autonomy outcome report.")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    args = parser.parse_args()
    repository = str(args.repository or "").strip()
    if not repository:
        raise SystemExit("repository is required")
    report = build_report(repository)
    print(json.dumps(report, indent=2, sort_keys=True))
    _write_summary(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
