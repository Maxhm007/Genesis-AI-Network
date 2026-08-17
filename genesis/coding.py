from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .intelligence_router import IntelligenceRouter
from .memory import GenesisMemory
from .providers import IntelligenceProvider, ProviderRegistry
from .self_learning import SelfLearningStore
from .selfdev import SelfDevelopmentExecutor, SelfDevResult


@dataclass(frozen=True)
class CodingProposal:
    title: str
    rationale: str
    files: dict[str, str]
    provider: str


class CodingModule:
    """Bounded software engineering module for Genesis."""

    MAX_CONTEXT_FILES = 4
    MAX_CONTEXT_BYTES = 12_000
    MAX_FILES = 6
    MAX_TOTAL_BYTES = 80_000
    MAX_EDITS = 1
    MAX_EDIT_BYTES = 4_000
    MAX_PROPOSAL_ATTEMPTS = 3
    MAX_REPAIR_ECHO_BYTES = 2_000

    def __init__(self, root: Path, providers: ProviderRegistry | None = None) -> None:
        self.root = root.resolve()
        self.providers = providers or ProviderRegistry()
        self.router = IntelligenceRouter(
            self.providers,
            telemetry_path=self.root / "runtime" / "provider_telemetry.json",
        )
        self.learning = SelfLearningStore(self.root / "runtime" / "self_learning.sqlite3")
        self.memory = GenesisMemory(self.root)
        self.executor = SelfDevelopmentExecutor(self.root)

    def _provider(self):
        try:
            return self.router.select("coding", complexity=0.75, require_non_bootstrap=True).provider
        except RuntimeError:
            pass

        live_candidates = []
        for provider in self.providers.available_providers():
            profile = IntelligenceRouter.profile(provider)
            if profile.name == "genesis-bootstrap":
                continue
            if "coding" not in profile.capabilities and "reasoning" not in profile.capabilities:
                continue
            live_candidates.append((profile.resource_cost, -profile.reliability, profile.name, provider))
        if live_candidates:
            live_candidates.sort(key=lambda item: (item[0], item[1], item[2]))
            return live_candidates[0][3]

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
    def _number_context(text: str) -> str:
        """Expose stable 1-based repository line locators without asking the model to copy source."""
        return "\n".join(f"{index}|{line}" for index, line in enumerate(text.splitlines(), start=1))

    @staticmethod
    def _balanced_json_object(text: str) -> str | None:
        start = text.find("{")
        while start >= 0:
            depth = 0
            in_string = False
            escaped = False
            for index in range(start, len(text)):
                char = text[index]
                if in_string:
                    if escaped:
                        escaped = False
                    elif char == "\\":
                        escaped = True
                    elif char == '"':
                        in_string = False
                    continue
                if char == '"':
                    in_string = True
                elif char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        return text[start : index + 1]
            start = text.find("{", start + 1)
        return None

    @classmethod
    def _extract_json(cls, raw: str) -> dict:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        try:
            value = json.loads(text)
        except json.JSONDecodeError as first_error:
            candidate = cls._balanced_json_object(text)
            if candidate is None:
                raise ValueError(f"provider did not return a complete JSON object: {first_error.msg}") from first_error
            try:
                value = json.loads(candidate)
            except json.JSONDecodeError as nested_error:
                raise ValueError(f"provider returned malformed JSON: {nested_error.msg}") from nested_error
        if not isinstance(value, dict):
            raise ValueError("coding proposal must be a JSON object")
        return value

    def _apply_line_edit(self, path: str, start_line: object, end_line: object, new: object) -> str:
        if not isinstance(start_line, int) or isinstance(start_line, bool):
            raise ValueError("line edit start_line must be an integer")
        if not isinstance(end_line, int) or isinstance(end_line, bool):
            raise ValueError("line edit end_line must be an integer")
        if not isinstance(new, str):
            raise ValueError("line edit new text must be a string")
        if start_line < 1 or end_line < start_line:
            raise ValueError("line edit range is invalid")

        target = (self.root / path).resolve()
        if not target.is_file():
            raise ValueError(f"edit target does not exist: {path}")
        current = target.read_text(encoding="utf-8")
        lines = current.splitlines(keepends=True)
        if end_line > len(lines):
            raise ValueError(f"line edit range exceeds file length: {path}")

        removed = "".join(lines[start_line - 1 : end_line])
        replacement = new
        if removed.endswith(("\n", "\r")) and replacement and not replacement.endswith(("\n", "\r")):
            replacement += "\n"
        return "".join(lines[: start_line - 1]) + replacement + "".join(lines[end_line:])

    def _files_from_edits(self, edits: object) -> dict[str, str]:
        if not isinstance(edits, list) or not edits or len(edits) > self.MAX_EDITS:
            raise ValueError("coding proposal edits count out of bounds")
        total = 0
        rendered: dict[str, str] = {}
        for edit in edits:
            if not isinstance(edit, dict):
                raise ValueError("each coding edit must be an object")
            path_value = edit.get("path")
            if not isinstance(path_value, str):
                raise ValueError("each coding edit requires a path")
            path = path_value.replace("\\", "/").lstrip("./")
            self.executor._validate_paths([path])

            if "start_line" in edit or "end_line" in edit:
                new = edit.get("new")
                if isinstance(new, str):
                    total += len(new.encode("utf-8"))
                if total > self.MAX_EDIT_BYTES:
                    raise ValueError("coding proposal edits exceed byte limit")
                rendered[path] = self._apply_line_edit(path, edit.get("start_line"), edit.get("end_line"), new)
                continue

            # Backward-compatible exact-text form for trusted callers. Autonomous prompts use line ranges.
            old = edit.get("old")
            new = edit.get("new")
            if not isinstance(old, str) or not isinstance(new, str) or not old:
                raise ValueError("coding edit requires start_line/end_line/new or legacy old/new text")
            total += len(old.encode("utf-8")) + len(new.encode("utf-8"))
            if total > self.MAX_EDIT_BYTES:
                raise ValueError("coding proposal edits exceed byte limit")
            current = rendered.get(path)
            if current is None:
                target = (self.root / path).resolve()
                if not target.is_file():
                    raise ValueError(f"edit target does not exist: {path}")
                current = target.read_text(encoding="utf-8")
            if current.count(old) != 1:
                raise ValueError(f"edit old text must match exactly once: {path}")
            rendered[path] = current.replace(old, new, 1)
        return rendered

    def validate_proposal(self, proposal: dict, provider_name: str) -> CodingProposal:
        if not isinstance(proposal, dict):
            raise ValueError("coding proposal must be a JSON object")
        raw_files = proposal.get("files")
        if isinstance(raw_files, dict):
            files = raw_files
        elif "edits" in proposal:
            files = self._files_from_edits(proposal.get("edits"))
        else:
            raise ValueError("coding proposal must contain a files mapping or compact edits list")
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
            title=str(proposal.get("title", "Genesis bounded coding candidate"))[:200],
            rationale=str(proposal.get("rationale", "one bounded repository edit"))[:4000],
            files={str(path): content for path, content in files.items()},
            provider=provider_name,
        )

    def _repair_prompt(self, original_prompt: str, raw: str, error: Exception, attempt: int) -> str:
        previous = raw.encode("utf-8", errors="replace")[: self.MAX_REPAIR_ECHO_BYTES].decode("utf-8", errors="replace")
        return (
            original_prompt
            + "\nRETRY: previous JSON was invalid.\n"
            + f"ERROR: {type(error).__name__}: {str(error)[:500]}\n"
            + f"PREVIOUS: {previous}\n"
            + 'Return ONLY: {"edits":[{"path":"existing allowed path","start_line":1,"end_line":1,"new":"replacement text"}]}. '
            + "Choose line numbers exactly from NUMBERED_CONTEXT. Exactly one edit. Do not copy old source text. "
            + "No title, rationale, markdown, commentary, new files, policy changes, test weakening, or protected paths.\n"
        )

    def propose(
        self,
        objective: str,
        context_paths: list[str] | None = None,
        *,
        provider: IntelligenceProvider | None = None,
    ) -> CodingProposal:
        objective = objective.strip()
        if not objective:
            raise ValueError("coding objective is required")
        provider = provider or self._provider()
        if provider is None:
            raise RuntimeError("no intelligence provider available")
        context = self.read_context(context_paths or [])
        numbered_context = {path: self._number_context(text) for path, text in context.items()}
        prompt = (
            "ROLE: bounded_coding_engineer\n"
            "TASK: Make exactly ONE smallest useful edit toward OBJECTIVE using only NUMBERED_CONTEXT.\n"
            'OUTPUT: JSON only: {"edits":[{"path":"existing allowed path","start_line":1,"end_line":1,"new":"replacement text"}]}\n'
            "RULES: exactly one edit; choose 1-based inclusive start_line/end_line from NUMBERED_CONTEXT; do NOT reproduce old source text; "
            "no title/rationale/markdown/explanation; do not create files. The local executor resolves those lines against the repository. "
            "Allowed paths: genesis/, tests/, docs/, config/, desktop/, mobile/. Never change Constitution, Genesis Block, .github, validation/quorum, permissions, secrets, or weaken tests.\n"
            f"OBJECTIVE: {objective}\n"
            f"NUMBERED_CONTEXT: {json.dumps(numbered_context, sort_keys=True)}\n"
        )
        current_prompt = prompt
        last_error: Exception | None = None
        for attempt in range(1, self.MAX_PROPOSAL_ATTEMPTS + 1):
            raw = provider.reason(current_prompt)
            try:
                return self.validate_proposal(self._extract_json(raw), provider.name)
            except (ValueError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt >= self.MAX_PROPOSAL_ATTEMPTS:
                    break
                current_prompt = self._repair_prompt(prompt, raw, exc, attempt)
        raise ValueError(
            f"coding provider failed to produce a valid proposal after {self.MAX_PROPOSAL_ATTEMPTS} bounded attempts: {last_error}"
        )

    def execute_candidate(self, proposal: CodingProposal) -> SelfDevResult:
        payload = {
            "title": proposal.title,
            "rationale": proposal.rationale,
            "files": proposal.files,
        }
        return self.executor.execute(payload)
