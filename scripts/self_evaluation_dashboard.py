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

OLD_EVOLUTION_SECTION = '''<section class="view" id="v-evolution"><div class="head"><div><h2>Self Evolution</h2><p>Measured evidence of learning, healing and development.</p></div></div><div class="grid"><div class="card s7"><div id="evoMetrics" class="metrics"></div></div><div class="card s5"><div class="stats"><div class="stat"><b id="wfSamples">—</b><span>Workflow samples</span></div><div class="stat"><b id="healSamples">—</b><span>Healing samples</span></div><div class="stat"><b id="devSamples">—</b><span>Development samples</span></div></div></div><div class="card s12"><div class="label">Recent Evolution Activity</div><div id="evoActivity" class="stack" style="margin-top:10px"></div></div></div></section>'''

NEW_EVOLUTION_SECTION = '''<section class="view" id="v-evolution"><div class="head"><div><h2>Self Evolution</h2><p>Measured evidence of learning, healing and development.</p></div></div><div class="grid"><div class="card s7"><div id="evoMetrics" class="metrics"></div></div><div class="card s5"><div class="stats"><div class="stat"><b id="wfSamples">—</b><span>Workflow samples</span></div><div class="stat"><b id="healSamples">—</b><span>Healing samples</span></div><div class="stat"><b id="devSamples">—</b><span>Development samples</span></div></div></div><div class="card s4"><div class="label">Completed Self-Development Tasks</div><div id="selfDevDone" class="value">—</div><div class="cap">Merged, validated Genesis candidate improvements</div></div><div class="card s8"><div class="label">What Genesis Improved</div><div id="selfDevHistory" class="stack" style="margin-top:10px"></div></div><div class="card s12"><div class="label">Recent Evolution Activity</div><div id="evoActivity" class="stack" style="margin-top:10px"></div></div></div></section>'''

OLD_RENDER = "$('#wfSamples').textContent=k.workflow_samples??0;$('#healSamples').textContent=k.healing_samples??0;$('#devSamples').textContent=k.development_samples??0;const act="
NEW_RENDER = "$('#wfSamples').textContent=k.workflow_samples??0;$('#healSamples').textContent=k.healing_samples??0;$('#devSamples').textContent=k.development_samples??0;$('#selfDevDone').textContent=k.completed_self_development_tasks??0;const devhist=(g.self_development_history||[]).map(x=>item(`#${x.number} ${x.title}`,`${x.improvement} · ${age(x.merged_at)}`,x.url)).join('')||'<div class=\"empty\">No completed self-development task found in this snapshot.</div>';$('#selfDevHistory').innerHTML=devhist;const act="


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
    for heading in ("Goal", "Changes", "Design"):
        text = _section(body, heading)
        if text:
            return text
    return str(pr.get("title") or "Validated Genesis self-development improvement")[:420]


def merged_self_development_prs(pulls: list[dict]) -> list[dict]:
    rows = []
    for pr in pulls:
        head = str((pr.get("head") or {}).get("ref") or "")
        if not pr.get("merged_at"):
            continue
        if not (head.startswith("genesis/candidate-") or head.startswith("genesis/privileged-candidate-")):
            continue
        rows.append(
            {
                "number": pr.get("number"),
                "title": str(pr.get("title") or "Genesis self-development"),
                "improvement": improvement_from_pr(pr),
                "head": head,
                "lane": "privileged" if head.startswith("genesis/privileged-candidate-") else "normal",
                "merged_at": pr.get("merged_at"),
                "url": pr.get("html_url"),
                "evidence": "merged validated Genesis candidate PR",
            }
        )
    rows.sort(key=lambda row: str(row.get("merged_at") or ""), reverse=True)
    return rows


def enrich_status(history: list[dict]) -> None:
    if not STATUS.is_file():
        return
    payload = json.loads(STATUS.read_text(encoding="utf-8"))
    gene0 = (payload.setdefault("genes", {})).setdefault("0", {})
    kpis = gene0.setdefault("kpis", {})
    kpis["completed_self_development_tasks"] = len(history)
    gene0["self_development_history"] = history[:20]
    payload.setdefault("network", {})["completed_self_development_tasks"] = len(history)
    payload["self_development_evaluation"] = {
        "completed_tasks": len(history),
        "recent_improvements": history[:20],
        "definition": "Merged Genesis candidate PRs that passed the repository validation/promotion path.",
    }
    STATUS.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def patch_dashboard() -> None:
    if not DASHBOARD.is_file():
        return
    html = DASHBOARD.read_text(encoding="utf-8")
    if "id=\"selfDevDone\"" not in html:
        if OLD_EVOLUTION_SECTION not in html:
            raise RuntimeError("Self Evolution dashboard contract changed; refusing blind patch")
        html = html.replace(OLD_EVOLUTION_SECTION, NEW_EVOLUTION_SECTION, 1)
    if "completed_self_development_tasks??0" not in html:
        if OLD_RENDER not in html:
            raise RuntimeError("Self Evolution render contract changed; refusing blind patch")
        html = html.replace(OLD_RENDER, NEW_RENDER, 1)
    DASHBOARD.write_text(html, encoding="utf-8")


def build() -> dict:
    pulls = safe_api(f"/repos/{OWNER}/{REPO}/pulls?state=closed&sort=updated&direction=desc&per_page=100", [])
    history = merged_self_development_prs(pulls if isinstance(pulls, list) else [])
    enrich_status(history)
    patch_dashboard()
    return {"completed_self_development_tasks": len(history), "recent_improvements": history[:20]}


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, sort_keys=True))
