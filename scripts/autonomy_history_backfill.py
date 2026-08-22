from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

OWNER = "Maxhm007"
REPO = "Genesis-AI-Network"
STATUS = Path("docs/status/status.json")
DASHBOARD = Path("docs/status/index.html")
SELFDEV_PREFIX = "Genesis self-development candidate:"

AUTONOMY_TRIAL_NAME = "genesis autonomy trial"
PROMOTION_STAGER_NAME = "genesis promotion stager"


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _is_genesis_ai(name: str, email: str) -> bool:
    name_key = re.sub(r"[^a-z0-9]+", "", _norm(name))
    email_key = _norm(email)
    return name_key == "genesisai" or email_key.startswith("genesis-ai@") or email_key.startswith("genesisai@")


def _classify_actor(author_name: str, author_email: str, committer_name: str, committer_email: str) -> str | None:
    if _is_genesis_ai(author_name, author_email):
        return "genesis_ai_authored"
    if _norm(author_name) == AUTONOMY_TRIAL_NAME and _norm(committer_name) == PROMOTION_STAGER_NAME:
        return "autonomy_trial_promoted"
    return None


def parse_git_history(text: str) -> tuple[list[dict[str, Any]], int]:
    """Parse full HEAD history and return trusted Genesis self-development evidence.

    The caller must provide a full, non-shallow repository history. Every row in
    the returned list is already reachable from the checked-out HEAD because it
    came directly from `git log HEAD`.
    """
    rows: list[dict[str, Any]] = []
    candidate_count = 0
    for raw in str(text or "").splitlines():
        parts = raw.split("\x1f")
        if len(parts) != 7:
            continue
        sha, author_name, author_email, committer_name, committer_email, authored_at, subject = parts
        if not subject.startswith(SELFDEV_PREFIX):
            continue
        candidate_count += 1
        provenance = _classify_actor(author_name, author_email, committer_name, committer_email)
        if provenance is None:
            continue
        rows.append(
            {
                "sha": sha,
                "title": re.sub(rf"^{re.escape(SELFDEV_PREFIX)}\s*", "", subject),
                "message": subject,
                "authored_at": authored_at,
                "author": author_name or "Genesis",
                "committer": committer_name or "Genesis",
                "url": f"https://github.com/{OWNER}/{REPO}/commit/{sha}",
                "provenance": provenance,
                "evidence": (
                    "Genesis AI authored self-development commit present in full deployed main history"
                    if provenance == "genesis_ai_authored"
                    else "Genesis Autonomy Trial change promoted by Genesis Promotion Stager and present in full deployed main history"
                ),
                "credit": "historical_autonomous_main_evidence",
            }
        )
    rows.sort(key=lambda row: str(row.get("authored_at") or ""), reverse=True)
    return rows, candidate_count


def _run_git(args: list[str], root: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def scan_local_main_history(root: Path = Path(".")) -> list[dict[str, Any]]:
    """Read self-development proof from the checked-out full Git history.

    Pages checks out main with fetch-depth: 0. We explicitly reject shallow
    repositories so a partial checkout can never silently publish false zeros.
    """
    shallow = _run_git(["rev-parse", "--is-shallow-repository"], root).lower()
    if shallow == "true":
        raise RuntimeError("Autonomy history requires a full git checkout; refusing to publish false zero evidence")

    fmt = "%H%x1f%an%x1f%ae%x1f%cn%x1f%ce%x1f%aI%x1f%s"
    history = _run_git(["log", "HEAD", f"--format={fmt}"], root)
    rows, candidate_count = parse_git_history(history)
    if candidate_count and not rows:
        raise RuntimeError(
            f"Found {candidate_count} self-development commit signatures but none matched trusted Genesis actors; refusing false zero evidence"
        )
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
    evaluation["history_source"] = "full_local_git_log_head"
    evaluation["definition"] = (
        "Strict verified cycles come only from the autonomy-proof ledger. Historical autonomous main evidence is a separate, "
        "source-control-backed count of Genesis AI authored self-development and Genesis Autonomy Trial changes found directly "
        "in the full deployed main Git history. Historical evidence does not retroactively become strict ledger credit. "
        "Assisted and owner work remain separate."
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
    rows = scan_local_main_history()
    enrich_status(rows)
    patch_dashboard()
    return {
        "historical_autonomous_main_evidence": len(rows),
        "genesis_authored_main_commits": sum(1 for row in rows if row.get("provenance") == "genesis_ai_authored"),
        "autonomy_trial_main_commits": sum(1 for row in rows if row.get("provenance") == "autonomy_trial_promoted"),
        "history_source": "full_local_git_log_head",
        "recent": rows[:30],
    }


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, sort_keys=True))
