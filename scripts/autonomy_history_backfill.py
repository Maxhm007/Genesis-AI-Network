from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

OWNER = "Maxhm007"
REPO = "Genesis-AI-Network"
TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
STATUS = Path("docs/status/status.json")
DASHBOARD = Path("docs/status/index.html")
SELFDEV_PREFIX = "Genesis self-development candidate:"
GENESIS_AI_LOGIN = "genesis-ai"
AUTONOMY_TRIAL_NAME = "genesis autonomy trial"
PROMOTION_STAGER_NAME = "genesis promotion stager"


def api(path: str) -> Any:
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "genesis-autonomy-history-backfill",
            **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def safe_api(path: str, default: Any) -> Any:
    try:
        return api(path)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
        return default


def _actor_name(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    return str(value.get("login") or value.get("name") or "").strip()


def _commit_message(detail: dict[str, Any]) -> str:
    return str((detail.get("commit") or {}).get("message") or "").splitlines()[0]


def _reachable_from_main(sha: str) -> bool:
    compare = safe_api(f"/repos/{OWNER}/{REPO}/compare/{sha}...main", {})
    if not isinstance(compare, dict):
        return False
    merge_base = compare.get("merge_base_commit") or {}
    status = str(compare.get("status") or "")
    return str(merge_base.get("sha") or "") == sha and status in {"ahead", "identical"}


def search_self_development_commits() -> list[dict[str, Any]]:
    """Find historical self-development commits and prove they are on main.

    Commit search avoids the old one-page author window. Every result is then
    fetched directly and ancestry-checked against main before it is displayed.
    """
    query = f'repo:{OWNER}/{REPO} "{SELFDEV_PREFIX}"'
    encoded = urllib.parse.urlencode({"q": query, "per_page": 100})
    result = safe_api(f"/search/commits?{encoded}", {"items": []})
    items = result.get("items", []) if isinstance(result, dict) else []

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        sha = str(item.get("sha") or "").strip()
        if not sha or sha in seen:
            continue
        seen.add(sha)
        detail = safe_api(f"/repos/{OWNER}/{REPO}/commits/{sha}", {})
        if not isinstance(detail, dict):
            continue
        message = _commit_message(detail)
        if not message.startswith(SELFDEV_PREFIX):
            continue
        if not _reachable_from_main(sha):
            continue

        author_actor = _actor_name(detail.get("author"))
        committer_actor = _actor_name(detail.get("committer"))
        commit_author = (detail.get("commit") or {}).get("author") or {}
        commit_committer = (detail.get("commit") or {}).get("committer") or {}
        author_name = author_actor or str(commit_author.get("name") or "")
        committer_name = committer_actor or str(commit_committer.get("name") or "")
        author_key = author_name.lower()
        committer_key = committer_name.lower()

        if author_key == GENESIS_AI_LOGIN:
            provenance = "genesis_ai_authored"
        elif author_key == AUTONOMY_TRIAL_NAME and committer_key == PROMOTION_STAGER_NAME:
            provenance = "autonomy_trial_promoted"
        else:
            continue

        rows.append(
            {
                "sha": sha,
                "title": re.sub(rf"^{re.escape(SELFDEV_PREFIX)}\s*", "", message),
                "message": message,
                "authored_at": commit_author.get("date"),
                "author": author_name or "Genesis",
                "committer": committer_name or "Genesis",
                "url": detail.get("html_url"),
                "provenance": provenance,
                "evidence": (
                    "Genesis AI authored self-development commit confirmed as an ancestor of main"
                    if provenance == "genesis_ai_authored"
                    else "Genesis Autonomy Trial change promoted by Genesis Promotion Stager and confirmed as an ancestor of main"
                ),
                "credit": "historical_autonomous_main_evidence",
            }
        )

    rows.sort(key=lambda row: str(row.get("authored_at") or ""), reverse=True)
    return rows


def enrich_status(rows: list[dict[str, Any]], path: Path = STATUS) -> None:
    if not path.is_file():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    evaluation = payload.setdefault("self_development_evaluation", {})
    attribution = evaluation.setdefault("attribution", {})

    genesis_ai = [row for row in rows if row.get("provenance") == "genesis_ai_authored"]
    trials = [row for row in rows if row.get("provenance") == "autonomy_trial_promoted"]

    evaluation["genesis_authored_main_commits"] = len(genesis_ai)
    evaluation["autonomy_trial_main_commits"] = len(trials)
    evaluation["historical_autonomous_main_evidence"] = len(rows)
    evaluation["recent_genesis_authored_main"] = rows[:30]
    evaluation["definition"] = (
        "Strict verified cycles come only from the autonomy-proof ledger. Historical autonomous main evidence is a separate, "
        "source-control-backed count of Genesis AI authored self-development and Genesis Autonomy Trial changes that are proven "
        "ancestors of main. Historical evidence does not retroactively become strict ledger credit. Assisted and owner work remain separate."
    )

    gene0 = payload.setdefault("genes", {}).setdefault("0", {})
    kpis = gene0.setdefault("kpis", {})
    kpis["genesis_authored_main_commits"] = len(genesis_ai)
    kpis["autonomy_trial_main_commits"] = len(trials)
    kpis["historical_autonomous_main_evidence"] = len(rows)
    gene0["genesis_authored_main_history"] = rows[:30]

    payload.setdefault("network", {})["historical_autonomous_main_evidence"] = len(rows)
    attribution.setdefault("genesis_autonomous", evaluation.get("autonomous_pr_promotions", 0))
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def patch_dashboard(path: Path = DASHBOARD) -> None:
    if not path.is_file():
        return
    html = path.read_text(encoding="utf-8")
    html = html.replace("Autonomous PR Promotions", "Automated Main Evidence")
    html = html.replace(
        "Merged candidate PRs carrying explicit Genesis autonomous provenance",
        "Historical Genesis AI / Autonomy Trial changes confirmed in main",
    )
    html = html.replace("Genesis-Authored Main History", "Historical Autonomous Main Evidence")
    html = html.replace(
        "$('#autoPr').textContent=sde.autonomous_pr_promotions??attr.genesis_autonomous??0;",
        "$('#autoPr').textContent=sde.historical_autonomous_main_evidence??sde.autonomous_pr_promotions??attr.genesis_autonomous??0;",
    )
    html = html.replace(
        "No Genesis-authored self-development commit was found in default-branch history.",
        "No historical Genesis autonomous self-development commit was confirmed in main history.",
    )
    path.write_text(html, encoding="utf-8")


def build() -> dict[str, Any]:
    rows = search_self_development_commits()
    enrich_status(rows)
    patch_dashboard()
    return {
        "historical_autonomous_main_evidence": len(rows),
        "genesis_authored_main_commits": sum(1 for row in rows if row.get("provenance") == "genesis_ai_authored"),
        "autonomy_trial_main_commits": sum(1 for row in rows if row.get("provenance") == "autonomy_trial_promoted"),
        "recent": rows[:30],
    }


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, sort_keys=True))
