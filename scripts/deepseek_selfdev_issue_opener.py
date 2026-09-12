from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVIDER_URL = os.environ.get("GENESIS_DEEPSEEK_DISCOVERY_URL", "http://127.0.0.1:8768").rstrip("/")
MODEL_ID = "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B"
DISCOVERY_LABEL = "genesis-deepseek-discovered"
SELFDEV_LABEL = "genesis-self-improvement"
AUTONOMOUS_LABEL = "genesis-autonomous"
OPEN_BACKLOG_CAP = max(1, int(os.environ.get("GENESIS_DEEPSEEK_DISCOVERY_OPEN_CAP", "3")))
FILES_PER_RUN = max(2, min(6, int(os.environ.get("GENESIS_DEEPSEEK_DISCOVERY_FILES", "4"))))
MAX_FILE_CHARS = 3500

PROTECTED_TARGETS = {
    "genesis/autonomy_guard.py",
    "genesis/autonomy_proof.py",
    "genesis/blockchain.py",
    "genesis/ephemeral_validator.py",
    "genesis/security.py",
    "genesis/selfdev.py",
    "genesis/issue_solver.py",
    "genesis/file_self_review.py",
    "genesis/file_self_review_policy.py",
    "scripts/secret_guard.py",
    "scripts/privileged_change_gate.py",
    "scripts/verify_validator_votes.py",
    "scripts/action_repair_guard.py",
    "scripts/issue_acceptance_guard.py",
}


def _github(method: str, path: str, payload: dict | None = None):
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token or not repo:
        raise RuntimeError("GITHUB_TOKEN and GITHUB_REPOSITORY are required")
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "Genesis-AI-Network/deepseek-selfdev-discovery",
        },
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw.strip() else {}


def _provider_reason(prompt: str) -> str:
    data = json.dumps({"prompt": prompt, "max_new_tokens": 640}).encode("utf-8")
    request = urllib.request.Request(
        f"{PROVIDER_URL}/reason",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=420) as response:
        payload = json.loads(response.read().decode("utf-8"))
    text = str(payload.get("response") or "").strip()
    if not text:
        raise RuntimeError("DeepSeek discovery provider returned no response")
    return text


def extract_json_object(text: str) -> dict:
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            value, _ = decoder.raw_decode(text[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("DeepSeek response did not contain a JSON object")


def safe_targets(root: Path = ROOT) -> list[str]:
    rows: list[str] = []
    for base in (root / "genesis", root / "scripts"):
        if not base.is_dir():
            continue
        for path in base.glob("*.py"):
            relative = path.relative_to(root).as_posix()
            if relative in PROTECTED_TARGETS or path.name.startswith("test_"):
                continue
            rows.append(relative)
    return sorted(set(rows))


def choose_targets(paths: list[str], seed: str, limit: int = FILES_PER_RUN) -> list[str]:
    if not paths:
        return []
    digest = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12], 16)
    start = digest % len(paths)
    rotated = paths[start:] + paths[:start]
    return rotated[: min(limit, len(rotated))]


def _file_context(root: Path, targets: list[str]) -> str:
    chunks: list[str] = []
    for relative in targets:
        text = (root / relative).read_text(encoding="utf-8", errors="replace")
        chunks.append(f"\n===== FILE: {relative} =====\n{text[:MAX_FILE_CHARS]}")
    return "".join(chunks)


def discovery_prompt(root: Path, targets: list[str]) -> str:
    context = _file_context(root, targets)
    return f"""ROLE: genesis_deepseek_agentic_self_development_discovery
You are DeepSeek acting as a bounded autonomous self-development reviewer for Genesis Gene 0.
Inspect ONLY the supplied current repository files. Find at most ONE concrete, testable, non-security-sensitive improvement or defect that can be solved by changing exactly one supplied Python target plus its focused test.
Do not invent missing behavior. The evidence field MUST be an exact substring copied from the chosen file. Prefer reliability, correctness, maintainability, agentic execution quality, issue lifecycle quality, or measurable capability improvements. Do not propose changes to security, signing, secrets, governance, workflow permissions, identity, or protected control files.
If there is no strong grounded issue, return {{"action":"none","reason":"..."}}.
Otherwise return JSON only in exactly this shape:
{{"action":"open_issue","target":"genesis/example.py","title":"short problem title","finding":"specific current problem and why it matters","evidence":"exact source substring","acceptance":"specific verifiable outcome and focused test expectation","priority":70}}
Priority must be an integer from 50 to 90.

CURRENT FILES:{context}
"""


def normalize_proposal(raw: dict, root: Path, allowed_targets: set[str]) -> dict | None:
    action = str(raw.get("action") or "").strip().lower()
    if action == "none":
        return None
    if action != "open_issue":
        raise ValueError("unsupported discovery action")
    target = str(raw.get("target") or "").strip().replace("\\", "/").lstrip("./")
    if target not in allowed_targets or target in PROTECTED_TARGETS:
        raise ValueError("DeepSeek selected an unreviewed or protected target")
    title = " ".join(str(raw.get("title") or "").split())[:180]
    finding = " ".join(str(raw.get("finding") or "").split())[:1800]
    evidence = str(raw.get("evidence") or "").strip()[:1200]
    acceptance = " ".join(str(raw.get("acceptance") or "").split())[:1800]
    if len(title) < 12 or len(finding) < 30 or len(evidence) < 8 or len(acceptance) < 25:
        raise ValueError("DeepSeek proposal is not sufficiently specific")
    current = (root / target).read_text(encoding="utf-8", errors="replace")
    if evidence not in current:
        raise ValueError("DeepSeek evidence is not an exact substring of current target")
    try:
        priority = int(raw.get("priority", 70))
    except (TypeError, ValueError):
        priority = 70
    priority = max(50, min(priority, 90))
    return {
        "target": target,
        "title": title,
        "finding": finding,
        "evidence": evidence,
        "acceptance": acceptance,
        "priority": priority,
    }


def fingerprint(proposal: dict) -> str:
    payload = "\n".join(
        [
            proposal["target"].lower(),
            proposal["title"].lower(),
            proposal["finding"].lower(),
            proposal["evidence"],
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def _labels() -> list[dict]:
    rows = _github("GET", "/labels?per_page=100")
    return rows if isinstance(rows, list) else []


def ensure_labels() -> None:
    existing = {str(row.get("name") or "") for row in _labels() if isinstance(row, dict)}
    definitions = {
        DISCOVERY_LABEL: ("6f42c1", "Self-development issue autonomously discovered by Gene 0 DeepSeek"),
        SELFDEV_LABEL: ("1d76db", "Genesis self-improvement work controlled through GitHub Issues"),
        AUTONOMOUS_LABEL: ("0e8a16", "Genesis autonomous issue lifecycle"),
    }
    for name, (color, description) in definitions.items():
        if name not in existing:
            _github("POST", "/labels", {"name": name, "color": color, "description": description})


def open_discovery_issues() -> list[dict]:
    encoded = DISCOVERY_LABEL.replace("-", "%2D")
    rows = _github("GET", f"/issues?state=open&labels={encoded}&per_page=100")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict) and "pull_request" not in row]


def issue_body(proposal: dict, fp: str) -> str:
    return (
        f"<!-- genesis-deepseek-selfdev:{fp} -->\n"
        "This issue was autonomously discovered by the dedicated DeepSeek self-development lane for Genesis Gene 0. "
        "The issue is the authoritative execution record; discovery itself does not modify code.\n\n"
        f"Genesis-Problem-Fingerprint: deepseek-selfdev:{fp}\n"
        "- **Task type:** `planned_self_improvement`\n"
        "- **Source:** `genesis.deepseek_agentic_discovery`\n"
        f"- **Model:** `{MODEL_ID}`\n"
        f"- **Priority:** {proposal['priority']}\n"
        f"- **Target:** `{proposal['target']}`\n\n"
        "### Finding\n"
        f"{proposal['finding']}\n\n"
        "### Grounding evidence\n"
        f"> {proposal['evidence']}\n\n"
        "### Objective\n"
        f"Resolve the grounded issue above with the smallest correct bounded change to `{proposal['target']}`.\n\n"
        "### Acceptance\n"
        f"{proposal['acceptance']}\n"
        "- Add or update focused regression coverage where appropriate.\n"
        "- Preserve existing security, validation, provenance, protected-file, signing, secret, and owner-control boundaries.\n"
        "- Full repository validation must pass before closure.\n"
        "- The same issue remains authoritative across retries; a failed solver attempt must comment evidence and keep it open.\n\n"
        "### Agentic ownership\n"
        "DeepSeek discovery identifies the problem; the separate DeepSeek agentic solver may claim and solve it. "
        "Discovery must not self-close or self-award verification.\n"
    )


def run(root: Path = ROOT, *, reasoner=_provider_reason) -> dict:
    root = Path(root).resolve()
    ensure_labels()
    backlog = open_discovery_issues()
    result: dict = {"status": "ok", "open_deepseek_selfdev": len(backlog), "created": None}
    if len(backlog) >= OPEN_BACKLOG_CAP:
        result.update(status="backlog_cap", reason=f"{len(backlog)} open DeepSeek self-development issues")
        return result

    paths = safe_targets(root)
    seed = os.environ.get("GENESIS_DEEPSEEK_DISCOVERY_SEED", "").strip() or os.environ.get("GITHUB_RUN_ID", "manual")
    targets = choose_targets(paths, seed)
    result["reviewed_targets"] = targets
    if not targets:
        result.update(status="no_targets")
        return result

    response = reasoner(discovery_prompt(root, targets))
    raw = extract_json_object(response)
    proposal = normalize_proposal(raw, root, set(targets))
    if proposal is None:
        result.update(status="no_issue", model_response=raw)
        return result

    fp = fingerprint(proposal)
    marker = f"<!-- genesis-deepseek-selfdev:{fp} -->"
    for issue in backlog:
        body = str(issue.get("body") or "")
        target_marker = f"- **Target:** `{proposal['target']}`"
        if marker in body or target_marker in body:
            result.update(status="duplicate_suppressed", duplicate_issue=int(issue.get("number") or 0), fingerprint=fp)
            return result

    title = f"[Genesis DeepSeek Self Development] {proposal['title']}"[:240]
    created = _github(
        "POST",
        "/issues",
        {
            "title": title,
            "body": issue_body(proposal, fp),
            "labels": [DISCOVERY_LABEL, SELFDEV_LABEL, AUTONOMOUS_LABEL],
        },
    )
    if not isinstance(created, dict) or int(created.get("number") or 0) <= 0:
        raise RuntimeError("GitHub did not create DeepSeek self-development issue")
    result["created"] = {
        "number": int(created["number"]),
        "url": str(created.get("html_url") or ""),
        "target": proposal["target"],
        "fingerprint": fp,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="DeepSeek agentic Gene 0 self-development issue opener")
    parser.add_argument("--output", type=Path, default=Path("runtime/deepseek_selfdev_discovery.json"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = run()
    except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError) as exc:
        result = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2, sort_keys=True))
        raise SystemExit(1)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
