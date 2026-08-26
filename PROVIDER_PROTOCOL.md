# Genesis Provider Protocol v0.1

Genesis AI must not depend on Codex, ChatGPT, Ollama, Gemini, DeepSeek, or any other named intelligence runtime for identity or basic operation.

The network therefore uses a tiny provider protocol.

## Health

`GET /health`

Any 2xx response means the provider is currently reachable.

## Reasoning

`POST /reason`

Request:

```json
{"prompt":"..."}
```

Response:

```json
{"response":"..."}
```

## Environment configuration

A Genesis node may connect to any compatible provider with:

```text
GENESIS_PROVIDER_URL=http://127.0.0.1:9000
GENESIS_PROVIDER_NAME=my-independent-provider
```

Multiple generic providers can also be configured through `GENESIS_PROVIDER_ENDPOINTS`.

No provider receives constitutional authority merely by being connected. Outputs remain candidate knowledge and candidate engineering work until separately validated.

## Local Qwen + DeepSeek coding runtime

Genesis uses open-weight models locally in the bounded Coding Intelligence Pulse. Qwen remains the primary coding model and DeepSeek is the default escalation/retry model:

```text
GENESIS_PULSE_FALLBACK_MODEL=Qwen/Qwen2.5-Coder-0.5B-Instruct
GENESIS_PULSE_ESCALATION_MODEL=deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B
```

Both checkpoints are downloaded through the existing Hugging Face/Transformers cache and executed on the GitHub Actions runner. There is no DeepSeek API key, paid DeepSeek service, or DeepSeek HTTP dependency in this path.

`deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B` is an open-weight DeepSeek-R1 distilled checkpoint. The runtime keeps the model ID configurable so Genesis can evaluate and adopt a better local DeepSeek checkpoint later without changing its identity or safety boundaries.

The adaptive local coding provider uses Qwen for the first bounded attempt and selects the configured escalation model when repository evidence indicates a revision/retry. If the escalation model fails to load or infer, the provider falls back to the primary Qwen model. Tests, Security, review, independent validation and promotion gates remain authoritative.

The larger GitHub Issue Autorepair lane continues using its existing local Qwen runtime to avoid loading another multi-billion-parameter checkpoint into the same standard runner. Provider-bound work that needs the Qwen + DeepSeek pairing is delegated to the dedicated Coding Intelligence Pulse.

## Bootstrap provider

Genesis includes `genesis-bootstrap`, a deterministic dependency-free provider. It exists so the AI-team workflow can continue planning, reviewing, validating structure, and identifying evidence gaps even when no trained model is available.

It is intentionally not presented as equivalent to a trained language model or scientific expert. It must not manufacture scientific facts.

## Future providers

A compatible provider can be:

- a locally hosted model;
- a remote model service;
- a distributed inference network;
- a specialist scientific model;
- a future model/runtime not known when Genesis was created.

The protocol, not the provider vendor, is the dependency boundary.
