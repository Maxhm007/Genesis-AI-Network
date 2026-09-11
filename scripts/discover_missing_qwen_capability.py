from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class CapabilityGap:
    capability_id: str
    title: str
    description: str
    detector_terms: tuple[tuple[str, ...], ...]
    reference: str
    priority: int = 72


BASELINE: tuple[CapabilityGap, ...] = (
    CapabilityGap(
        "structured_output_schema",
        "Schema-constrained structured output",
        "Generate and validate machine-readable output against an explicit schema instead of relying on free-form text.",
        (("json schema",), ("structured output",), ("schema validation", "model output")),
        "https://platform.openai.com/docs/guides/structured-outputs",
    ),
    CapabilityGap(
        "tool_call_planning",
        "Multi-step tool-call planning",
        "Plan, execute, verify, and revise bounded sequences of tool calls instead of treating each tool call as an isolated action.",
        (("tool planning",), ("tool-call planning",), ("function calling", "plan"), ("tool use", "planner")),
        "https://github.com/langchain-ai/langgraph",
    ),
    CapabilityGap(
        "retrieval_grounding",
        "Retrieval-grounded answer generation",
        "Ground model output in retrieved evidence with provenance and reject unsupported claims when evidence is absent.",
        (("retrieval", "ground"), ("rag",), ("provenance", "retrieval")),
        "https://github.com/huggingface/transformers",
    ),
    CapabilityGap(
        "context_compaction",
        "Long-context compaction",
        "Compress or summarize older context while preserving task-critical state so long-running agents can continue reliably.",
        (("context compaction",), ("context compression",), ("long context", "summary")),
        "https://github.com/vllm-project/vllm",
    ),
    CapabilityGap(
        "multimodal_vision",
        "Image understanding",
        "Accept image inputs and derive grounded visual observations that can be used by Genesis reasoning and tools.",
        (("vision", "image"), ("multimodal", "image"), ("image understanding",)),
        "https://github.com/huggingface/transformers",
    ),
    CapabilityGap(
        "audio_understanding",
        "Audio and speech understanding",
        "Process bounded audio or speech inputs into structured evidence usable by Genesis.",
        (("audio", "speech"), ("speech recognition",), ("audio understanding",)),
        "https://github.com/huggingface/transformers",
    ),
    CapabilityGap(
        "computer_use",
        "Computer-use interaction",
        "Observe and act on graphical interfaces through a bounded, verifiable computer-use loop.",
        (("computer use",), ("gui", "automation"), ("screen", "click", "verify")),
        "https://github.com/microsoft/autogen",
    ),
    CapabilityGap(
        "self_verification",
        "Self-verification before completion",
        "Require an independent verification pass that checks evidence and acceptance criteria before work is considered complete.",
        (("self verification",), ("self-verification",), ("independent validation",), ("verify", "acceptance")),
        "https://github.com/microsoft/autogen",
    ),
    CapabilityGap(
        "persistent_memory",
        "Persistent agent memory",
        "Store and retrieve bounded long-lived task knowledge across runs with explicit provenance and lifecycle controls.",
        (("persistent memory",), ("long-term memory",), ("memory store",), ("sqlite", "memory")),
        "https://github.com/microsoft/autogen",
    ),
    CapabilityGap(
        "model_routing",
        "Capability-aware model routing",
        "Route a task to the best available model/provider based on required capability, reliability, cost, and fallback evidence.",
        (("model routing",), ("provider fallback",), ("capability routing",), ("route", "provider", "capability")),
        "https://github.com/vllm-project/vllm",
    ),
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def repository_text(root: Path = ROOT) -> str:
    chunks: list[str] = []
    for folder in (root / "genesis", root / "scripts"):
        if not folder.exists():
            continue
        for path in folder.rglob("*.py"):
            if path.name == Path(__file__).name:
                continue
            try:
                chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
    return _normalize("\n".join(chunks))


def capability_present(gap: CapabilityGap, corpus: str) -> bool:
    for alternative in gap.detector_terms:
        if all(_normalize(term) in corpus for term in alternative):
            return True
    return False


def fingerprint(capability_id: str) -> str:
    return hashlib.sha256(capability_id.encode("utf-8")).hexdigest()[:16]


def choose_missing(corpus: str, issue_texts: Iterable[str]) -> CapabilityGap | None:
    issues = "\n".join(issue_texts).lower()
    for gap in BASELINE:
        marker = f"genesis-missing-capability:{fingerprint(gap.capability_id)}"
        if marker in issues:
            continue
        if capability_present(gap, corpus):
            continue
        return gap
    return None


def _request_json(url: str, token: str) -> object:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Genesis-AI-Network/missing-capability-discovery",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, token: str, payload: dict) -> object:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Genesis-AI-Network/missing-capability-discovery",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def all_issue_texts(repo: str, token: str) -> list[str]:
    texts: list[str] = []
    for page in range(1, 11):
        url = f"https://api.github.com/repos/{repo}/issues?" + urllib.parse.urlencode(
            {"state": "all", "per_page": 100, "page": page}
        )
        rows = _request_json(url, token)
        if not isinstance(rows, list):
            break
        for row in rows:
            if isinstance(row, dict) and "pull_request" not in row:
                texts.append(f"{row.get('title') or ''}\n{row.get('body') or ''}")
        if len(rows) < 100:
            break
    return texts


def issue_body(gap: CapabilityGap) -> str:
    fp = fingerprint(gap.capability_id)
    task_id = f"task-missing-{fp}"
    return f"""<!-- genesis-missing-capability:{fp} -->
<!-- genesis-task-id:{task_id} -->
This GitHub Issue is the authoritative task record for one capability that the Qwen-based Genesis baseline is missing.

Genesis-Problem-Fingerprint: missing-qwen-capability:{fp}
- **Genesis task ID:** `{task_id}`
- **Task type:** `new_capability`
- **Capability subtype:** `missing_capability`
- **Source:** `genesis.qwen_gap_audit`
- **Priority:** {gap.priority}
- **Target:** `genesis/learned_capabilities.py`

### Missing capability
**{gap.title}**

{gap.description}

### Why this issue exists
The independent Missing Capability Discovery task compared the current Genesis source tree against its maintained modern capability baseline and found no implementation evidence for `{gap.capability_id}`.
Reference capability evidence: {gap.reference}

### Objective
Add the smallest bounded executable capability that closes this gap for the Qwen-based Genesis system. Qwen remains the base model; this task upgrades what Genesis can do around that base model.

### Acceptance
- Add an executable capability or integration that demonstrably closes the named gap.
- Add focused tests proving the capability works and fails safely.
- Preserve Security, validation, provenance, protected-file boundaries, signing boundaries, secret boundaries, and owner control.
- Do not self-award benchmark or capability score.
- Existing Issue Solver and bounded repair process remain the only implementation lane.

### Discovery rule
This Missing Capability Discovery task only opens the issue. It does not implement, promote, repair, or close it.
"""


def create_issue(repo: str, token: str, gap: CapabilityGap) -> str:
    payload = {
        "title": f"[Genesis Task] missing capability — {gap.title}",
        "body": issue_body(gap),
        "labels": ["genesis-task", "genesis-capability-discovery"],
    }
    result = _post_json(f"https://api.github.com/repos/{repo}/issues", token, payload)
    if not isinstance(result, dict):
        raise RuntimeError("invalid GitHub issue response")
    return str(result.get("html_url") or result.get("url") or "")


def main() -> int:
    parser = argparse.ArgumentParser(description="Open at most one issue for one missing Qwen/Genesis capability.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo = str(os.environ.get("GITHUB_REPOSITORY") or "").strip()
    token = str(os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    if not repo:
        print(json.dumps({"status": "no_repository"}, sort_keys=True))
        return 0
    if not token and not args.dry_run:
        print(json.dumps({"status": "no_token"}, sort_keys=True))
        return 0

    corpus = repository_text(ROOT)
    issues = all_issue_texts(repo, token) if token else []
    gap = choose_missing(corpus, issues)
    if gap is None:
        print(json.dumps({"status": "no_missing_capability"}, sort_keys=True))
        return 0

    payload = {
        "status": "missing_capability_found",
        "capability_id": gap.capability_id,
        "title": gap.title,
        "fingerprint": fingerprint(gap.capability_id),
    }
    if args.dry_run:
        payload["issue_body"] = issue_body(gap)
        print(json.dumps(payload, sort_keys=True))
        return 0

    payload["issue_url"] = create_issue(repo, token, gap)
    payload["status"] = "missing_capability_issue_created"
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
