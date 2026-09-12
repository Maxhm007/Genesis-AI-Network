from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass


PEER_REPOS = (
    ("Gene 002", "Maxhm007/Genesis-Node-2"),
    ("Gene 003", "Maxhm007/Genesis-Node-3"),
)
CANONICAL_REPO = "Maxhm007/Genesis-AI-Network"
MARKER_PREFIX = "<!-- genesis-peer-sync:"


@dataclass(frozen=True)
class PeerIssue:
    gene: str
    repository: str
    number: int
    title: str
    body: str
    html_url: str

    @property
    def fingerprint(self) -> str:
        seed = f"{self.repository}#{self.number}\n{self.title}\n{self.body}".encode("utf-8", "replace")
        return hashlib.sha256(seed).hexdigest()[:20]

    @property
    def marker(self) -> str:
        return f"{MARKER_PREFIX}{self.repository}#{self.number}:{self.fingerprint} -->"


def is_actionable(issue: dict) -> bool:
    if issue.get("pull_request"):
        return False
    if str(issue.get("state") or "").lower() != "open":
        return False
    title = str(issue.get("title") or "").strip()
    body = str(issue.get("body") or "").strip()
    if not title or not body:
        return False
    lowered = f"{title}\n{body}".lower()
    return any(token in lowered for token in (
        "acceptance", "objective", "problem", "failure", "fails", "repair", "fix", "bug", "issue", "improvement"
    ))


def normalize_peer_issue(gene: str, repository: str, issue: dict) -> PeerIssue:
    return PeerIssue(
        gene=gene,
        repository=repository,
        number=int(issue["number"]),
        title=str(issue.get("title") or "").strip(),
        body=str(issue.get("body") or "").strip(),
        html_url=str(issue.get("html_url") or "").strip(),
    )


def canonical_title(peer: PeerIssue) -> str:
    return f"[Peer Sync][{peer.gene}] {peer.title}"[:256]


def canonical_body(peer: PeerIssue) -> str:
    return (
        f"{peer.marker}\n"
        "This GitHub Issue is the Gene 0 authoritative copy of an actionable peer finding.\n\n"
        f"- **Source Gene:** {peer.gene}\n"
        f"- **Source repository:** `{peer.repository}`\n"
        f"- **Source issue:** #{peer.number}\n"
        f"- **Source URL:** {peer.html_url}\n"
        f"- **Peer-sync fingerprint:** `{peer.fingerprint}`\n\n"
        "### Peer finding\n"
        f"{peer.body[:12000]}\n\n"
        "### Gene 0 authority rule\n"
        "Gene 2 and Gene 3 may discover and report problems, but Gene 0 owns the canonical issue lifecycle. "
        "This copy must pass normal Genesis routing, deduplication, tests, Security, validation, and verify-before-close controls. "
        "Do not create another successor issue merely because one solve attempt fails.\n"
    )


def _request(method: str, url: str, token: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Genesis-Gene-Peer-Issue-Sync",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_open_peer_issues(token: str) -> list[PeerIssue]:
    rows: list[PeerIssue] = []
    for gene, repo in PEER_REPOS:
        url = f"https://api.github.com/repos/{repo}/issues?state=open&per_page=100&sort=created&direction=asc"
        for issue in _request("GET", url, token):
            if is_actionable(issue):
                rows.append(normalize_peer_issue(gene, repo, issue))
    return rows


def fetch_canonical_issue_bodies(token: str) -> list[str]:
    url = f"https://api.github.com/repos/{CANONICAL_REPO}/issues?state=all&per_page=100"
    rows = _request("GET", url, token)
    return [str(row.get("body") or "") for row in rows if not row.get("pull_request")]


def choose_new_peer_issue(peers: list[PeerIssue], canonical_bodies: list[str]) -> PeerIssue | None:
    corpus = "\n".join(canonical_bodies)
    for peer in sorted(peers, key=lambda row: (row.repository, row.number)):
        if peer.marker not in corpus:
            return peer
    return None


def create_canonical_issue(peer: PeerIssue, token: str) -> dict:
    url = f"https://api.github.com/repos/{CANONICAL_REPO}/issues"
    return _request(
        "POST",
        url,
        token,
        {
            "title": canonical_title(peer),
            "body": canonical_body(peer),
            "labels": ["genesis-autonomous", "gene-peer-sync"],
        },
    )


def run(token: str) -> dict:
    peers = fetch_open_peer_issues(token)
    bodies = fetch_canonical_issue_bodies(token)
    selected = choose_new_peer_issue(peers, bodies)
    if selected is None:
        return {"status": "no_new_peer_issue", "peer_open_actionable": len(peers)}
    created = create_canonical_issue(selected, token)
    return {
        "status": "created",
        "source_gene": selected.gene,
        "source_repository": selected.repository,
        "source_issue": selected.number,
        "canonical_issue": created.get("number"),
        "fingerprint": selected.fingerprint,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync one new actionable Gene 2/3 issue into Gene 0")
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""))
    args = parser.parse_args()
    if not args.token:
        raise SystemExit("GITHUB_TOKEN is required")
    try:
        print(json.dumps(run(args.token), sort_keys=True))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise SystemExit(f"GitHub API error {exc.code}: {body[:1000]}") from exc


if __name__ == "__main__":
    main()
