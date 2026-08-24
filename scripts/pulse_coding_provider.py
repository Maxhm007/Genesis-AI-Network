from __future__ import annotations

import argparse
import json
import os
import textwrap
from http.server import ThreadingHTTPServer

from local_reasoning_provider import Handler, LocalReasoningModel


DEFAULT_MODEL = os.environ.get(
    "GENESIS_PULSE_FALLBACK_MODEL",
    "Qwen/Qwen2.5-Coder-0.5B-Instruct",
)
DEFAULT_ESCALATION_MODEL = os.environ.get(
    "GENESIS_PULSE_ESCALATION_MODEL",
    "Qwen/Qwen2.5-Coder-1.5B-Instruct",
)
DEFAULT_MAX_NEW_TOKENS = 384
DEFAULT_ESCALATION_MAX_NEW_TOKENS = 128
ESCALATION_MAX_PROMPT_CHARS = 8_000
MAX_NOOP_CORRECTIONS = 2
REVISION_MARKERS = (
    "PREVIOUS_DEVELOPMENT_FEEDBACK:",
    "PREVIOUS_PIPELINE_FEEDBACK:",
    "RETRY:",
)


class AdaptiveCodingModel:
    """Use stronger bounded reasoning when prior evidence says a coding revision is needed.

    First-pass coding remains on the small replaceable model. Revision/retry prompts escalate to
    a stronger replaceable model. The stronger model has its own compact generation budget so a
    bounded one-edit correction does not consume the whole provider request deadline. The provider
    also detects compact edits that would reproduce the exact repository text from NUMBERED_CONTEXT
    and self-corrects them inside the same pulse.
    """

    def __init__(
        self,
        primary_model_id: str,
        escalation_model_id: str | None,
        *,
        max_new_tokens: int,
        escalation_max_new_tokens: int = DEFAULT_ESCALATION_MAX_NEW_TOKENS,
    ) -> None:
        self.primary_model_id = primary_model_id
        self.escalation_model_id = (escalation_model_id or "").strip() or None
        self.model_id = primary_model_id
        self.max_new_tokens = max_new_tokens
        self.escalation_max_new_tokens = max(64, min(int(escalation_max_new_tokens), max_new_tokens))
        self._models: dict[str, LocalReasoningModel] = {}

    def _selected_model_id(self, prompt: str) -> str:
        if self.escalation_model_id and any(marker in prompt for marker in REVISION_MARKERS):
            return self.escalation_model_id
        return self.primary_model_id

    def _model_budget(self, model_id: str) -> int:
        if self.escalation_model_id and model_id == self.escalation_model_id:
            return self.escalation_max_new_tokens
        return self.max_new_tokens

    def _model(self, model_id: str) -> LocalReasoningModel:
        model = self._models.get(model_id)
        if model is None:
            model = LocalReasoningModel(model_id, max_new_tokens=self._model_budget(model_id))
            self._models[model_id] = model
        return model

    @staticmethod
    def _compact_escalation_prompt(prompt: str) -> str:
        if len(prompt) <= ESCALATION_MAX_PROMPT_CHARS:
            return prompt
        head = ESCALATION_MAX_PROMPT_CHARS // 2
        tail = ESCALATION_MAX_PROMPT_CHARS - head
        return prompt[:head] + "\n[...escalation context elided...]\n" + prompt[-tail:]

    def _reason_once(self, prompt: str, max_new_tokens: int | None) -> str:
        selected_model_id = self._selected_model_id(prompt)
        is_escalation = selected_model_id != self.primary_model_id
        selected_prompt = self._compact_escalation_prompt(prompt) if is_escalation else prompt
        selected_budget = max_new_tokens
        if is_escalation:
            selected_budget = self.escalation_max_new_tokens if max_new_tokens is None else min(
                int(max_new_tokens), self.escalation_max_new_tokens
            )
        print(
            json.dumps(
                {
                    "event": "coding_model_selected",
                    "model": selected_model_id,
                    "revision": is_escalation,
                    "max_new_tokens": selected_budget,
                    "prompt_chars": len(selected_prompt),
                }
            ),
            flush=True,
        )
        try:
            return self._model(selected_model_id).reason(selected_prompt, max_new_tokens=selected_budget)
        except Exception as exc:
            if selected_model_id == self.primary_model_id:
                raise
            print(
                json.dumps(
                    {
                        "event": "coding_model_fallback",
                        "from_model": selected_model_id,
                        "to_model": self.primary_model_id,
                        "error": type(exc).__name__,
                    }
                ),
                flush=True,
            )
            return self._model(self.primary_model_id).reason(prompt, max_new_tokens=max_new_tokens)

    @staticmethod
    def _proposal_object(raw: str) -> dict | None:
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
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start < 0 or end <= start:
                return None
            try:
                value = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
        return value if isinstance(value, dict) else None

    @staticmethod
    def _numbered_context(prompt: str) -> dict[str, str]:
        marker = "NUMBERED_CONTEXT: "
        for line in prompt.splitlines():
            if not line.startswith(marker):
                continue
            try:
                value = json.loads(line[len(marker) :])
            except json.JSONDecodeError:
                return {}
            if isinstance(value, dict):
                return {str(path): str(text) for path, text in value.items()}
        return {}

    @staticmethod
    def _source_range(numbered_text: str, start_line: int, end_line: int) -> str | None:
        source_lines: dict[int, str] = {}
        for entry in numbered_text.splitlines():
            number, separator, text = entry.partition("|")
            if not separator:
                continue
            try:
                source_lines[int(number)] = text
            except ValueError:
                continue
        if start_line < 1 or end_line < start_line:
            return None
        try:
            return "\n".join(source_lines[line] for line in range(start_line, end_line + 1))
        except KeyError:
            return None

    @staticmethod
    def _first_nonblank_indent(text: str) -> str:
        for line in text.splitlines():
            if line.strip():
                return line[: len(line) - len(line.lstrip(" \t"))]
        return ""

    @classmethod
    def _normalized_line_replacement(cls, path: str, existing: str, replacement: str) -> str:
        """Mirror only the line-replacement normalization performed by CodingModule."""
        if not path.endswith(".py"):
            return replacement
        target_indent = cls._first_nonblank_indent(existing)
        replacement_indent = cls._first_nonblank_indent(replacement)
        if not target_indent or not replacement.strip():
            return replacement
        if len(replacement_indent.expandtabs(8)) >= len(target_indent.expandtabs(8)):
            return replacement
        dedented = textwrap.dedent(replacement)
        return textwrap.indent(dedented, target_indent, predicate=lambda line: bool(line.strip()))

    @classmethod
    def _is_noop_edit(cls, prompt: str, raw: str) -> bool:
        proposal = cls._proposal_object(raw)
        if proposal is None:
            return False

        edits = proposal.get("edits")
        if isinstance(edits, dict):
            edits = [edits]
        elif not isinstance(edits, list):
            edit = proposal.get("edit")
            if isinstance(edit, dict):
                edits = [edit]
            elif isinstance(proposal.get("path"), str) and isinstance(proposal.get("new"), str):
                edits = [proposal]
            else:
                edits = None

        if isinstance(edits, list) and len(edits) == 1 and isinstance(edits[0], dict):
            edit = edits[0]
            old = edit.get("old")
            new = edit.get("new")
            if isinstance(old, str) and isinstance(new, str) and old == new:
                return True
            path = edit.get("path")
            start_line = edit.get("start_line")
            end_line = edit.get("end_line")
            if (
                isinstance(path, str)
                and isinstance(start_line, int)
                and not isinstance(start_line, bool)
                and isinstance(end_line, int)
                and not isinstance(end_line, bool)
                and isinstance(new, str)
            ):
                numbered = cls._numbered_context(prompt).get(path)
                if numbered is not None:
                    existing = cls._source_range(numbered, start_line, end_line)
                    if existing is not None:
                        normalized_new = cls._normalized_line_replacement(path, existing, new)
                        if normalized_new == existing:
                            return True

        files = proposal.get("files")
        if isinstance(files, dict) and len(files) == 1:
            path, new_content = next(iter(files.items()))
            if isinstance(path, str) and isinstance(new_content, str):
                numbered = cls._numbered_context(prompt).get(path)
                if numbered is not None:
                    existing_lines = []
                    for entry in numbered.splitlines():
                        _, separator, text = entry.partition("|")
                        if separator:
                            existing_lines.append(text)
                    if new_content == "\n".join(existing_lines):
                        return True
        return False

    @staticmethod
    def _noop_retry_prompt(prompt: str, raw: str, correction: int) -> str:
        previous = raw.encode("utf-8", errors="replace")[:1200].decode("utf-8", errors="replace")
        return (
            prompt
            + "\nRETRY: previous edit was a NO-OP and would make no repository change. "
            + "Use OBJECTIVE and NUMBERED_CONTEXT to choose a materially different replacement or a different relevant line. "
            + "Do not repeat the same line/replacement and do not broaden scope. Return only the required one-edit JSON.\n"
            + f"NOOP_CORRECTION_ATTEMPT: {correction}\n"
            + f"PREVIOUS_NOOP: {previous}\n"
        )

    def reason(self, prompt: str, max_new_tokens: int | None = None) -> str:
        base_prompt = prompt
        current_prompt = base_prompt
        raw = ""
        for correction in range(MAX_NOOP_CORRECTIONS + 1):
            raw = self._reason_once(current_prompt, max_new_tokens)
            if not self._is_noop_edit(base_prompt, raw):
                return raw
            if correction >= MAX_NOOP_CORRECTIONS:
                break
            print(
                json.dumps(
                    {
                        "event": "coding_noop_detected",
                        "correction": correction + 1,
                    }
                ),
                flush=True,
            )
            current_prompt = self._noop_retry_prompt(base_prompt, raw, correction + 1)
        return raw


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--escalation-model", default=DEFAULT_ESCALATION_MODEL)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=int(os.environ.get("GENESIS_PROVIDER_MAX_NEW_TOKENS", str(DEFAULT_MAX_NEW_TOKENS))),
    )
    parser.add_argument(
        "--escalation-max-new-tokens",
        type=int,
        default=int(
            os.environ.get(
                "GENESIS_PULSE_ESCALATION_MAX_NEW_TOKENS",
                str(DEFAULT_ESCALATION_MAX_NEW_TOKENS),
            )
        ),
    )
    args = parser.parse_args()

    Handler.model = AdaptiveCodingModel(
        args.model,
        args.escalation_model,
        max_new_tokens=args.max_new_tokens,
        escalation_max_new_tokens=args.escalation_max_new_tokens,
    )
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(
        json.dumps(
            {
                "status": "ready",
                "provider": "genesis-pulse-local-coding-fallback",
                "model": args.model,
                "escalation_model": args.escalation_model,
                "escalation_max_new_tokens": Handler.model.escalation_max_new_tokens,
                "replaceable": True,
                "adaptive_retry_escalation": True,
                "noop_self_correction": True,
            }
        ),
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
