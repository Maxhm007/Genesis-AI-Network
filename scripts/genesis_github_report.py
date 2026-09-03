from __future__ import annotations

import json
from pathlib import Path

from genesis_hourly_ops import render_email


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"


def main() -> None:
    """Render the hourly operations report without creating a persistent GitHub Issue.

    The owner retired the GitHub report-thread delivery channel. Operational report
    generation remains available as runtime evidence, but this script must not create,
    reopen, or comment on GitHub Issues. Real operational problems continue to be
    represented by their normal Issue-backed automation records.
    """
    subject, body = render_email()
    RUNTIME.mkdir(parents=True, exist_ok=True)
    report_path = RUNTIME / "genesis_hourly_report.txt"
    report_path.write_text(body.rstrip() + "\n", encoding="utf-8")
    result = {
        "status": "local_only",
        "github_issue_channel": "retired",
        "subject": subject,
        "report_path": str(report_path.relative_to(ROOT)),
    }
    (RUNTIME / "github_hourly_report_status.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
