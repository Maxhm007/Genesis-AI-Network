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

NEW_EVOLUTION_SECTION = '''<section class="view" id="v-evolution"><div class="head"><div><h2>Self Evolution</h2><p>Measured evidence of learning, healing and development with strict attribution.</p></div></div><div class="grid"><div class="card s7"><div id="evoMetrics" class="metrics"></div></div><div class="card s5"><div class="stats"><div class="stat"><b id="wfSamples">—</b><span>Workflow samples</span></div><div class="stat"><b id="healSamples">—</b><span>Healing samples</span></div><div class="stat"><b id="devSamples">—</b><span>Development samples</span></div></div></div><div class="card s4"><div class="label">Genesis Autonomous Development</div><div id="autoDevDone" class="value">—</div><div class="cap">Genesis-initiated work with autonomous provenance</div></div><div class="card s4"><div class="label">Assisted Development</div><div id="assistedDevDone" class="value">—</div><div class="cap">Assistant/external initiated or completed engineering</div></div><div class="card s4"><div class="label">Owner Development</div><div id="ownerDevDone" class="value">—</div><div class="cap">Owner/user initiated or authorized engineering</div></div><div class="card s12"><div class="label">Attributed Development History</div><div id="attributedDevHistory" class="stack" style="margin-top:10px"></div></div><div class="card s12"><div class="label">Recent Evolution Activity</div><div id="evoActivity" class="stack" style="margin-top:10px"></div></div></div></section>'''


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
    """Compatibility helper: only genuinely autonomous development."""
    return [row for row in attributed_development_prs(pulls) if row["attribution"] == "genesis_autonomous"]


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


def enrich_status(history: list[dict]) -> None:
    if not STATUS.is_file():
        return
    counts = summarize(history)
    payload = json.loads(STATUS.read_text(encoding="utf-8"))
    gene0 = (payload.setdefault("genes", {})).setdefault("0", {})
    kpis = gene0.setdefault("kpis", {})
    kpis["completed_self_development_tasks"] = counts["genesis_autonomous"]
    kpis["assisted_development_tasks"] = counts["assisted"]
    kpis["owner_development_tasks"] = counts["owner"]
    gene0["self_development_history"] = [row for row in history if row["attribution"] == "genesis_autonomous"][:20]
    gene0["development_attribution"] = counts
    gene0["attributed_development_history"] = history[:30]
    payload.setdefault("network", {})["completed_self_development_tasks"] = counts["genesis_autonomous"]
    payload["self_development_evaluation"] = {
        "completed_tasks": counts["genesis_autonomous"],
        "attribution": counts,
        "recent_improvements": history[:30],
        "definition": (
            "Genesis Autonomous requires explicit autonomous provenance. Assisted includes assistant/external/manual "
            "candidate work. Owner includes owner/* or explicitly owner-attributed work. Buckets are mutually exclusive."
        ),
    }
    STATUS.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def patch_dashboard() -> None:
    if not DASHBOARD.is_file():
        return
    html = DASHBOARD.read_text(encoding="utf-8")
    section_pattern = r'<section class="view" id="v-evolution">.*?</section>'
    if not re.search(section_pattern, html, flags=re.S):
        raise RuntimeError("Self Evolution section not found; refusing blind dashboard patch")
    html = re.sub(section_pattern, NEW_EVOLUTION_SECTION, html, count=1, flags=re.S)

    render_marker = "$('#wfSamples').textContent=k.workflow_samples??0;$('#healSamples').textContent=k.healing_samples??0;$('#devSamples').textContent=k.development_samples??0;"
    attribution_render = (
        "const da=(g.development_attribution||s.self_development_evaluation?.attribution||{});"
        "$('#autoDevDone').textContent=da.genesis_autonomous??0;"
        "$('#assistedDevDone').textContent=da.assisted??0;"
        "$('#ownerDevDone').textContent=da.owner??0;"
        "const dh=(g.attributed_development_history||s.self_development_evaluation?.recent_improvements||[]);"
        "$('#attributedDevHistory').innerHTML=dh.map(x=>item(`[${(x.attribution||'unknown').replace('_',' ')}] #${x.number??'—'} ${x.title||'Development'}`,`${x.improvement||''} · ${age(x.merged_at)}`,x.url)).join('')||'<div class=\"empty\">No attributed development evidence in this snapshot.</div>';"
    )
    if attribution_render not in html:
        if render_marker not in html:
            raise RuntimeError("Self Evolution render marker not found; refusing blind dashboard patch")
        html = html.replace(render_marker, render_marker + attribution_render, 1)
    DASHBOARD.write_text(html, encoding="utf-8")


def build() -> dict:
    pulls = safe_api(f"/repos/{OWNER}/{REPO}/pulls?state=closed&sort=updated&direction=desc&per_page=100", [])
    history = attributed_development_prs(pulls if isinstance(pulls, list) else [])
    enrich_status(history)
    patch_dashboard()
    return {"attribution": summarize(history), "recent_improvements": history[:30]}


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, sort_keys=True))
