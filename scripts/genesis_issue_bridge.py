from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from genesis.communication import GenesisCommunicator


def _event_payload() -> dict:
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")
    if not event_path:
        raise RuntimeError("GITHUB_EVENT_PATH is unavailable")
    return json.loads(Path(event_path).read_text(encoding="utf-8"))


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    event = _event_payload()
    issue = event.get("issue") or {}
    issue_number = int(issue["number"])
    issue_title = str(issue.get("title", ""))
    labels = {str(item.get("name", "")).lower() for item in issue.get("labels", [])}

    # Only explicitly opted-in communication threads are handled.
    if "genesis-chat" not in labels and not issue_title.lower().startswith("genesis chat"):
        print(json.dumps({"status": "ignored", "reason": "not a Genesis chat thread"}))
        return

    comment = event.get("comment")
    if isinstance(comment, dict):
        sender = str((comment.get("user") or {}).get("login", "github-user"))
        message = str(comment.get("body", ""))
    else:
        sender = str((issue.get("user") or {}).get("login", "github-user"))
        message = str(issue.get("body", ""))

    # Ignore Genesis's own replies to prevent response loops.
    actor = str((event.get("sender") or {}).get("login", ""))
    if actor in {"github-actions[bot]", "genesis-ai"}:
        print(json.dumps({"status": "ignored", "reason": "self reply"}))
        return

    result = GenesisCommunicator(root).reply(sender, message)
    response = result["genesis_response"]
    capability = result["capability_summary"]
    body = (
        f"**Genesis:**\n\n{response}\n\n"
        f"---\nOperational capability: {capability['score']}/{capability['max_score']} "
        f"({capability['percent']}%). This score measures operational readiness, not consciousness or general intelligence."
    )

    repo = os.environ["GITHUB_REPOSITORY"]
    subprocess.run(
        ["gh", "issue", "comment", str(issue_number), "--repo", repo, "--body", body],
        cwd=root,
        check=True,
        env=os.environ.copy(),
    )
    print(json.dumps({"status": "replied", "issue": issue_number, "sender": sender}))


if __name__ == "__main__":
    main()
