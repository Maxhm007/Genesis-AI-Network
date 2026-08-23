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
DEFAULT_MAX_NEW_TOKENS = 384


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=int(os.environ.get("GENESIS_PROVIDER_MAX_NEW_TOKENS", str(DEFAULT_MAX_NEW_TOKENS))),
    )
    args = parser.parse_args()

    # This entrypoint is intentionally separate from the retired historical
    # foundation runtime. It exposes only the existing provider protocol and the
    # selected model remains replaceable through GENESIS_PULSE_FALLBACK_MODEL.
    Handler.model = LocalReasoningModel(args.model, max_new_tokens=args.max_new_tokens)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(
        json.dumps(
            {
                "status": "ready",
                "provider": "genesis-pulse-local-coding-fallback",
                "model": args.model,
                "replaceable": True,
            }
        ),
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
