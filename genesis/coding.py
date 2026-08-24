from __future__ import annotations

import ast
import json
import re
import textwrap
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
    def _tokens(text: str) -> set[str]:
        return {token.lower() for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text)}

    @classmethod
    def _best_edit_hint(cls, objective: str, context: dict[str, str]) -> tuple[str, int]:
        """Ground the JSON example on the most objective-relevant repository line.

        Small local models often copy schema examples literally. A hard-coded line 1 therefore
        becomes an accidental instruction. Derive the example locator from the actual numbered
        context so copying the example is at least grounded in repository evidence.
        """
        if not context:
            return "", 1
        objective_lower = objective.lower()
        objective_tokens = cls._tokens(objective)
        best: tuple[int, int, int, int, int, str, int] | None = None
        for path_index, (path, text) in enumerate(context.items()):
            for line_number, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                overlap = len(objective_tokens & cls._tokens(stripped))
                exact_bonus = 100 if stripped.lower() in objective_lower else 0
                marker_bonus = 200 if "INSERTION_POINT" in stripped and stripped.lower() in objective_lower else 0
                score = overlap + exact_bonus + marker_bonus
                rank = (score, marker_bonus, exact_bonus, -path_index, -line_number)
                if best is None or rank > best[:5]:
                    best = (*rank, path, line_number)
        if best is not None:
            return best[5], best[6]
        first_path, first_text = next(iter(context.items()))
        return first_path, max(1, len(first_text.splitlines()))

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

    @staticmethod
    def _first_nonblank_indent(text: str) -> str:
        for line in text.splitlines():
            if line.strip():
                return line[: len(line) - len(line.lstrip(" \t"))]
        return ""

    @classmethod
    def _normalize_python_replacement(cls, removed: str, replacement: str) -> str:
        """Keep a compact Python line edit at the indentation level it replaces.

        Small local coding models often return syntactically useful statements without the
        repository indentation shown in NUMBERED_CONTEXT. Replacing an indented statement with
        that raw text can erase the only body of a try/except/if block. Preserve relative
        indentation locally; broader structural edits must explicitly replace the parent lines.
        """
        target_indent = cls._first_nonblank_indent(removed)
        replacement_indent = cls._first_nonblank_indent(replacement)
        if not target_indent or not replacement.strip():
            return replacement
        if len(replacement_indent.expandtabs(8)) >= len(target_indent.expandtabs(8)):
            return replacement
        dedented = textwrap.dedent(replacement)
        return textwrap.indent(dedented, target_indent, predicate=lambda line: bool(line.strip()))

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
        if path.endswith(".py") and "from __future__ import" in removed and "from __future__ import" not in new:
            raise ValueError("line edit may not overwrite a Python __future__ import")
        replacement = self._normalize_python_replacement(removed, new) if path.endswith(".py") else new
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
        for path, content in files.items():
            if str(path).endswith(".py"):
                try:
                    ast.parse(content, filename=str(path))
                except SyntaxError as exc:
                    location = f"{exc.lineno}:{exc.offset}" if exc.lineno else "unknown"
                    raise ValueError(
                        f"coding proposal creates invalid Python syntax in {path} at {location}: {exc.msg}"
                    ) from exc
        return CodingProposal(
            title=str(proposal.get("title", "Genesis bounded coding candidate"))[:200],
            rationale=str(proposal.get("rationale", "one bounded repository edit"))[:4000],
            files={str(path): content for path, content in files.items()},
            provider=provider_name,
        )

    def _repair_prompt(
        self,
        original_prompt: str,
        raw: str,
        error: Exception,
        attempt: int,
        allowed_paths: tuple[str, ...],
        edit_hint: tuple[str, int],
    ) -> str:
        previous = raw.encode("utf-8", errors="replace")[: self.MAX_REPAIR_ECHO_BYTES].decode("utf-8", errors="replace")
        preferred_path, preferred_line = edit_hint
        if not preferred_path and allowed_paths:
            preferred_path = allowed_paths[0]
        example = json.dumps(
            {"edits": [{"path": preferred_path, "start_line": preferred_line, "end_line": preferred_line, "new": "replacement text"}]},
            separators=(",", ":"),
        )
        return (
            original_prompt
            + "\nRETRY: previous JSON was invalid. Change strategy using ERROR and repository evidence; do not repeat the rejected edit.\n"
            + f"ERROR: {type(error).__name__}: {str(error)[:500]}\n"
            + f"PREVIOUS: {previous}\n"
            + f"VALID_PATHS: {json.dumps(allowed_paths)}\n"
            + f"GROUNDED_LINE_HINT: {preferred_path}:{preferred_line}\n"
            + f"Return ONLY the same JSON shape as: {example}. "
            + "The hint is derived from OBJECTIVE/NUMBERED_CONTEXT; verify it before using it and never copy an unrelated line number. "
            + "Copy the path exactly from VALID_PATHS/NUMBERED_CONTEXT. Do not invent, summarize, rename, or substitute the path. "
            + "Choose line numbers exactly from NUMBERED_CONTEXT. Exactly one edit. Do not copy old source text. "
            + "For Python, prefer replacing one complete standalone statement; do not remove the only body of try/except/if/for/while/with/class/def blocks. "
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
        allowed_paths = tuple(numbered_context)
        edit_hint = self._best_edit_hint(objective, context)
        preferred_path, preferred_line = edit_hint
        if not preferred_path and allowed_paths:
            preferred_path = allowed_paths[0]
            edit_hint = (preferred_path, preferred_line)
        output_example = json.dumps(
            {"edits": [{"path": preferred_path, "start_line": preferred_line, "end_line": preferred_line, "new": "replacement text"}]},
            separators=(",", ":"),
        )
        prompt = (
            "ROLE: bounded_coding_engineer\n"
            "TASK: Make exactly ONE smallest useful edit toward OBJECTIVE using only NUMBERED_CONTEXT.\n"
            f"OUTPUT: JSON only in this shape: {output_example}\n"
            f"VALID_PATHS: {json.dumps(allowed_paths)}\n"
            f"GROUNDED_LINE_HINT: {preferred_path}:{preferred_line}\n"
            "RULES: exactly one edit; path must match one key from VALID_PATHS exactly; choose 1-based inclusive start_line/end_line from NUMBERED_CONTEXT; do NOT reproduce old source text; "
            "the example/hint is grounded but must be verified against OBJECTIVE and NUMBERED_CONTEXT; never copy an unrelated example line number; "
            "never emit placeholder path text; no title/rationale/markdown/explanation; do not create files. The local executor resolves those lines against the repository and preserves local Python indentation. "
            "For Python, replace a complete standalone statement rather than deleting the only body of a compound block. "
            "Allowed path prefixes: genesis/, tests/, docs/, config/, desktop/, mobile/. Never change Constitution, Genesis Block, .github, validation/quorum, permissions, secrets, or weaken tests.\n"
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
                current_prompt = self._repair_prompt(prompt, raw, exc, attempt, allowed_paths, edit_hint)
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
