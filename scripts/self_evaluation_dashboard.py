from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

OWNER = "Maxhm007"
REPO = "Genesis-AI-Network"
TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
STATUS = Path("docs/status/status.json")
DASHBOARD = Path("docs/status/index.html")

AUTO_TITLE_PREFIX = "Genesis autonomous candidate:"
AUTO_BODY_MARKER = "Autonomous Genesis candidate. Promotion requires the Genesis Candidate PR Gate"
PROOF_MARKER = "<!-- genesis-autonomy-proof:genesis_autonomous -->"
ASSISTED_MARKERS = ("assistant-initiated", "assistant-created", "chatgpt", "assisted development")
OWNER_MARKERS = ("owner-authorized", "owner-initiated", "owner development")
SELFDEV_COMMIT_PREFIX = "Genesis self-development candidate:"

AUTONOMY_SECTION = '''<section class="view" id="view-autonomy">
  <div class="head"><div><h2>Autonomous Development</h2><p>Separate historical Genesis-authored development from strict end-to-end autonomous promotion proof.</p></div></div>
  <div class="grid">
    <div class="card s3"><div class="label">Strict Verified Cycles</div><div id="autoStrict" class="value">—</div><div class="cap">Genesis initiated + independently validated + promotion confirmed on main</div></div>
    <div class="card s3"><div class="label">Autonomous PR Promotions</div><div id="autoPr" class="value">—</div><div class="cap">Merged candidate PRs carrying explicit Genesis autonomous provenance</div></div>
    <div class="card s3"><div class="label">Genesis-Authored on Main</div><div id="autoMain" class="value">—</div><div class="cap">Historical self-development commits authored by Genesis AI in default-branch history</div></div>
    <div class="card s3"><div class="label">Assisted / Owner</div><div id="autoOther" class="value">—</div><div id="autoOtherCap" class="cap">Kept outside autonomous credit</div></div>
    <div class="card s6"><div class="label">Genesis-Authored Main History</div><div id="autoMainHistory" class="stack" style="margin-top:10px"></div></div>
    <div class="card s6"><div class="label">Attributed Promotion History</div><div id="autoPromotionHistory" class="stack" style="margin-top:10px"></div></div>
    <div class="card s12"><div class="label">Proof Rule</div><div id="autoDefinition" class="cap" style="margin-top:8px"></div></div>
  </div>
</section>'''


def api(path: str):
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "genesis-self-evaluation-dashboard",
            **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def safe_api(path: str, default):
    try:
        return api(path)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
        return default


def _section(body: str, heading: str) -> str:
    match = re.search(rf"(?ims)^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)", body or "")
    if not match:
        return ""
    text = re.sub(r"[`*_>#]", "", match.group(1))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:420]


def improvement_from_pr(pr: dict) -> str:
    body = str(pr.get("body") or "")
    for heading in ("Goal", "Changes", "Design", "What changed"):
        text = _section(body, heading)
        if text:
            return text
    return str(pr.get("title") or "Genesis development improvement")[:420]


def has_autonomous_provenance(pr: dict) -> bool:
    title = str(pr.get("title") or "")
    body = str(pr.get("body") or "")
    ordinary = title.startswith(AUTO_TITLE_PREFIX) and AUTO_BODY_MARKER in body
    explicit = PROOF_MARKER in body
    return ordinary or explicit


def classify_pr_attribution(pr: dict) -> str:
    """Put one merged development PR into exactly one attribution bucket."""
    head = str((pr.get("head") or {}).get("ref") or "")
    body = str(pr.get("body") or "").lower()
    if has_autonomous_provenance(pr):
        return "genesis_autonomous"
    if head.startswith("owner/") or any(marker in body for marker in OWNER_MARKERS):
        return "owner"
    return "assisted"


def attributed_development_prs(pulls: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for pr in pulls:
        if not pr.get("merged_at"):
            continue
        head = str((pr.get("head") or {}).get("ref") or "")
        development_branch = (
            head.startswith("genesis/candidate-")
            or head.startswith("genesis/privileged-candidate-")
            or head.startswith("owner/")
        )
        if not development_branch:
            continue
        attribution = classify_pr_attribution(pr)
        rows.append(
            {
                "number": pr.get("number"),
                "title": str(pr.get("title") or "Genesis development"),
                "improvement": improvement_from_pr(pr),
                "head": head,
                "lane": "privileged" if "privileged-candidate" in head else ("owner" if head.startswith("owner/") else "normal"),
                "merged_at": pr.get("merged_at"),
                "url": pr.get("html_url"),
                "attribution": attribution,
                "classification": attribution,
                "evidence": (
                    "Genesis autonomous provenance" if attribution == "genesis_autonomous"
                    else "owner provenance" if attribution == "owner"
                    else "assisted/manual provenance"
                ),
            }
        )
    rows.sort(key=lambda row: str(row.get("merged_at") or ""), reverse=True)
    return rows


def merged_self_development_prs(pulls: list[dict]) -> list[dict]:
    """Compatibility helper: only PRs with explicit autonomous provenance."""
    return [row for row in attributed_development_prs(pulls) if row["attribution"] == "genesis_autonomous"]


def genesis_authored_main_commits(commits: list[dict]) -> list[dict]:
    """Historical proof that Genesis-authored self-development is present on main.

    GitHub's repository commit-list endpoint without a sha parameter walks the
    default branch. Filtering it by the genesis-ai account therefore gives
    commit evidence reachable from main. This is intentionally NOT upgraded to
    strict autonomous-cycle credit; the promotion-proof ledger remains stricter.
    """
    rows: list[dict] = []
    for commit in commits:
        message = str((commit.get("commit") or {}).get("message") or "").splitlines()[0]
        if not message.startswith(SELFDEV_COMMIT_PREFIX):
            continue
        author = (commit.get("commit") or {}).get("author") or {}
        rows.append(
            {
                "sha": commit.get("sha"),
                "title": re.sub(rf"^{re.escape(SELFDEV_COMMIT_PREFIX)}\s*", "", message),
                "message": message,
                "authored_at": author.get("date"),
                "author": author.get("name") or "Genesis AI",
                "url": commit.get("html_url"),
                "evidence": "Genesis AI authored self-development commit present in default-branch history",
                "credit": "historical_genesis_authored_main",
            }
        )
    rows.sort(key=lambda row: str(row.get("authored_at") or ""), reverse=True)
    return rows


def summarize(history: list[dict]) -> dict:
    auto = [row for row in history if row["attribution"] == "genesis_autonomous"]
    assisted = [row for row in history if row["attribution"] == "assisted"]
    owner = [row for row in history if row["attribution"] == "owner"]
    return {
        "genesis_autonomous": len(auto),
        "assisted": len(assisted),
        "owner": len(owner),
        "total": len(history),
    }


def enrich_status(history: list[dict], authored_main: list[dict]) -> None:
    if not STATUS.is_file():
        return
    counts = summarize(history)
    payload = json.loads(STATUS.read_text(encoding="utf-8"))
    strict = int((payload.get("verified_autonomy") or {}).get("autonomous_promotions", 0) or 0)

    gene0 = (payload.setdefault("genes", {})).setdefault("0", {})
    kpis = gene0.setdefault("kpis", {})
    kpis["completed_self_development_tasks"] = counts["genesis_autonomous"]
    kpis["assisted_development_tasks"] = counts["assisted"]
    kpis["owner_development_tasks"] = counts["owner"]
    kpis["genesis_authored_main_commits"] = len(authored_main)
    kpis["strict_verified_autonomous_cycles"] = strict
    gene0["self_development_history"] = [row for row in history if row["attribution"] == "genesis_autonomous"][:20]
    gene0["development_attribution"] = counts
    gene0["attributed_development_history"] = history[:30]
    gene0["genesis_authored_main_history"] = authored_main[:30]

    payload.setdefault("network", {})["completed_self_development_tasks"] = counts["genesis_autonomous"]
    payload["self_development_evaluation"] = {
        "strict_verified_cycles": strict,
        "autonomous_pr_promotions": counts["genesis_autonomous"],
        "genesis_authored_main_commits": len(authored_main),
        "attribution": counts,
        "recent_improvements": history[:30],
        "recent_genesis_authored_main": authored_main[:30],
        "definition": (
            "Strict verified cycle means Genesis initiated the work and the autonomy-proof ledger confirms independent validation and promotion on main. "
            "Genesis-authored on main is historical source-control proof that Genesis AI authored self-development now present in default-branch history, "
            "but it is shown separately because older commits may predate complete ledger provenance. Assisted and owner work never increase autonomous credit."
        ),
    }
    STATUS.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def patch_dashboard() -> None:
    """Patch Command Center v2 at build time with an Autonomous Development view."""
    if not DASHBOARD.is_file():
        return
    html = DASHBOARD.read_text(encoding="utf-8")

    nav_anchor = '<button data-view="evolution">Capability Evolution</button>'
    if 'data-view="autonomy"' not in html:
        if nav_anchor not in html:
            raise RuntimeError("Command Center v2 navigation marker not found; refusing blind dashboard patch")
        html = html.replace(nav_anchor, nav_anchor + '\n    <button data-view="autonomy">Autonomous Development</button>', 1)

    if 'id="view-autonomy"' not in html:
        section_anchor = '<section class="view" id="view-issues">'
        if section_anchor not in html:
            raise RuntimeError("Command Center v2 section marker not found; refusing blind dashboard patch")
        html = html.replace(section_anchor, AUTONOMY_SECTION + '\n' + section_anchor, 1)

    if "autonomy:['Autonomous Development'" not in html:
        names_anchor = "evolution:['Capability Evolution','Benchmark-driven learning and measured improvement'],issues:"
        if names_anchor not in html:
            raise RuntimeError("Command Center v2 view-name marker not found; refusing blind dashboard patch")
        html = html.replace(
            names_anchor,
            "evolution:['Capability Evolution','Benchmark-driven learning and measured improvement'],autonomy:['Autonomous Development','Genesis-authored development and strict promotion proof'],issues:",
            1,
        )

    render_marker = "$('#autonomyCap').textContent=`Assisted ${auto.assisted_promotions??0} · Owner ${auto.owner_promotions??0}`;"
    render_extension = """const sde=DATA.self_development_evaluation||{},attr=sde.attribution||{};$('#autoStrict').textContent=sde.strict_verified_cycles??auto.autonomous_promotions??0;$('#autoPr').textContent=sde.autonomous_pr_promotions??attr.genesis_autonomous??0;$('#autoMain').textContent=sde.genesis_authored_main_commits??0;$('#autoOther').textContent=`${attr.assisted??0} / ${attr.owner??0}`;$('#autoOtherCap').textContent=`Assisted ${attr.assisted??0} · Owner ${attr.owner??0}`;const authored=(sde.recent_genesis_authored_main||[]);$('#autoMainHistory').innerHTML=authored.map(x=>item(x.title||x.message,`${x.author||'Genesis AI'} · ${age(x.authored_at)} · ${(x.sha||'').slice(0,10)}`,x.url,'good')).join('')||'<div class=\"empty\">No Genesis-authored self-development commit was found in default-branch history.</div>';const promoted=(sde.recent_improvements||[]);$('#autoPromotionHistory').innerHTML=promoted.map(x=>item(`[${(x.attribution||'unknown').replaceAll('_',' ')}] #${x.number??'—'} ${x.title||'Development'}`,`${x.improvement||''} · ${age(x.merged_at)}`,x.url,cls(x.attribution==='genesis_autonomous'?'complete':'review'))).join('')||'<div class=\"empty\">No attributed candidate-PR promotion evidence in this snapshot.</div>';$('#autoDefinition').textContent=sde.definition||'Strict autonomous credit requires Genesis initiation, independent validation and confirmed promotion on main.';"""
    if render_extension not in html:
        if render_marker not in html:
            raise RuntimeError("Command Center v2 autonomy render marker not found; refusing blind dashboard patch")
        html = html.replace(render_marker, render_marker + render_extension, 1)

    DASHBOARD.write_text(html, encoding="utf-8")


def build() -> dict:
    pulls = safe_api(f"/repos/{OWNER}/{REPO}/pulls?state=closed&sort=updated&direction=desc&per_page=100", [])
    history = attributed_development_prs(pulls if isinstance(pulls, list) else [])

    # REST list-commits with author filter walks default-branch history, which is
    # stronger evidence than searching arbitrary repository branches.
    commits = safe_api(f"/repos/{OWNER}/{REPO}/commits?author=genesis-ai&per_page=100", [])
    authored_main = genesis_authored_main_commits(commits if isinstance(commits, list) else [])

    counts = summarize(history)
    enrich_status(history, authored_main)
    patch_dashboard()
    return {
        "strict_verified_cycles": None,
        "completed_self_development_tasks": counts["genesis_autonomous"],
        "genesis_authored_main_commits": len(authored_main),
        "attribution": counts,
        "recent_improvements": history[:30],
        "recent_genesis_authored_main": authored_main[:30],
    }


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, sort_keys=True))
