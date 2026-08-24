from __future__ import annotations

import argparse
import json
import os
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
REVISION_MARKERS = (
    "PREVIOUS_DEVELOPMENT_FEEDBACK:",
    "PREVIOUS_PIPELINE_FEEDBACK:",
    "RETRY:",
)


class AdaptiveCodingModel:
    """Use a stronger replaceable coding model only when prior evidence says revision is needed.

    First-pass coding remains on the small bounded model. A revision/retry prompt escalates to
    a stronger model so Genesis does not repeatedly ask the same weak model to repair its own
    failed candidate. Both model IDs remain configuration-driven and the primary model is used
    as an availability fallback if the escalation model cannot load or reason successfully.
    """

    def __init__(
        self,
        primary_model_id: str,
        escalation_model_id: str | None,
        *,
        max_new_tokens: int,
    ) -> None:
        self.primary_model_id = primary_model_id
        self.escalation_model_id = (escalation_model_id or "").strip() or None
        self.model_id = primary_model_id
        self.max_new_tokens = max_new_tokens
        self._models: dict[str, LocalReasoningModel] = {}

    def _selected_model_id(self, prompt: str) -> str:
        if self.escalation_model_id and any(marker in prompt for marker in REVISION_MARKERS):
            return self.escalation_model_id
        return self.primary_model_id

    def _model(self, model_id: str) -> LocalReasoningModel:
        model = self._models.get(model_id)
        if model is None:
            model = LocalReasoningModel(model_id, max_new_tokens=self.max_new_tokens)
            self._models[model_id] = model
        return model

    def reason(self, prompt: str, max_new_tokens: int | None = None) -> str:
        selected_model_id = self._selected_model_id(prompt)
        try:
            return self._model(selected_model_id).reason(prompt, max_new_tokens=max_new_tokens)
        except Exception:
            if selected_model_id == self.primary_model_id:
                raise
            return self._model(self.primary_model_id).reason(prompt, max_new_tokens=max_new_tokens)


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
    args = parser.parse_args()

    # This entrypoint is intentionally separate from the retired historical
    # foundation runtime. It exposes only the existing provider protocol and both
    # selected models remain replaceable through environment/CLI configuration.
    Handler.model = AdaptiveCodingModel(
        args.model,
        args.escalation_model,
        max_new_tokens=args.max_new_tokens,
    )
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(
        json.dumps(
            {
                "status": "ready",
                "provider": "genesis-pulse-local-coding-fallback",
                "model": args.model,
                "escalation_model": args.escalation_model,
                "replaceable": True,
                "adaptive_retry_escalation": True,
            }
        ),
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
