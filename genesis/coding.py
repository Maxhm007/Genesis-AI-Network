from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .intelligence_router import IntelligenceRouter
from .providers import ProviderRegistry
from .selfdev import SelfDevelopmentExecutor, SelfDevResult


@dataclass(frozen=True)
class CodingProposal:
    title: str
    rationale: str
    files: dict[str, str]
    provider: str


class CodingModule:
    """Codex-like bounded software engineering module for Genesis.

    It can inspect supplied context, ask a replaceable intelligence provider to
    draft complete-file candidate edits, validate paths through the existing
    self-development sandbox, and execute only as an isolated candidate branch.
    It cannot modify protected identity files, GitHub workflow permissions, or
    bypass tests/independent validation.
    """

    MAX_CONTEXT_FILES = 8
    MAX_CONTEXT_BYTES = 64_000
    MAX_FILES = 6
    MAX_TOTAL_BYTES = 80_000

    def __init__(self, root: Path, providers: ProviderRegistry | None = None) -> None:
        self.root = root.resolve()
        self.providers = providers or ProviderRegistry()
        self.router = IntelligenceRouter(self.providers)
        self.executor = SelfDevelopmentExecutor(self.root)

    def _provider(self):
        try:
            return self.router.select("coding", complexity=0.75, require_non_bootstrap=True).provider
        except RuntimeError:
            # Bootstrap may still be used for low-risk deterministic planning,
            # but only when no stronger provider is available.
            try:
                return self.router.select("coding", complexity=0.2).provider
            except RuntimeError:
                return None

    def read_context(self, paths: list[str]) -> dict[str, str]:
        context: dict[str, str] = {}
        total = 0
        for relative in paths[: self.MAX_CONTEXT_FILES]:
            normalized = str(relative).replace("\\", "/").lstrip("./")
            self.executor._validate_paths([normalized])
            path = (self.root / normalized).resolve()
            if not path.is_file():
                continue
            data = path.read_bytes()
            remaining = self.MAX_CONTEXT_BYTES - total
            if remaining <= 0:
                break
            text = data[:remaining].decode("utf-8", errors="replace")
            context[normalized] = text
            total += len(text.encode("utf-8"))
        return context

    @staticmethod
    def _extract_json(raw: str) -> dict:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        return json.loads(text)

    def validate_proposal(self, proposal: dict, provider_name: str) -> CodingProposal:
        if not isinstance(proposal, dict) or not isinstance(proposal.get("files"), dict):
            raise ValueError("coding proposal must contain a files mapping")
        files = proposal["files"]
        if not files or len(files) > self.MAX_FILES:
            raise ValueError("coding proposal file count out of bounds")
        paths = [str(path) for path in files]
        self.executor._validate_paths(paths)
        total = sum(len(str(content).encode("utf-8")) for content in files.values())
        if total > self.MAX_TOTAL_BYTES:
            raise ValueError("coding proposal exceeds byte limit")
        if not all(isinstance(content, str) for content in files.values()):
            raise ValueError("coding proposal contents must be text")
        return CodingProposal(
            title=str(proposal.get("title", "Genesis coding candidate"))[:200],
            rationale=str(proposal.get("rationale", ""))[:4000],
            files={str(path): content for path, content in files.items()},
            provider=provider_name,
        )

    def propose(self, objective: str, context_paths: list[str] | None = None) -> CodingProposal:
        objective = objective.strip()
        if not objective:
            raise ValueError("coding objective is required")
        provider = self._provider()
        if provider is None:
            raise RuntimeError("no intelligence provider available")
        context = self.read_context(context_paths or [])
        prompt = (
            "ROLE: coding_engineer\n"
            "PURPOSE: Create the smallest safe software candidate for Genesis AI Network.\n"
            "RULES: Return JSON only with title, rationale, and files mapping relative paths to COMPLETE replacement contents. "
            "Only genesis/, tests/, docs/, and config/ are writable. Never modify Genesis Constitution, Genesis Block, .github workflows, "
            "validation/quorum rules, permissions, or secrets. Do not weaken tests. Keep changes bounded and reversible.\n"
            f"OBJECTIVE: {objective}\n"
            f"CONTEXT: {json.dumps(context, sort_keys=True)}\n"
        )
        raw = provider.reason(prompt)
        return self.validate_proposal(self._extract_json(raw), provider.name)

    def execute_candidate(self, proposal: CodingProposal) -> SelfDevResult:
        payload = {
            "title": proposal.title,
            "rationale": proposal.rationale,
            "files": proposal.files,
        }
        return self.executor.execute(payload)
