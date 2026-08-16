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

No provider receives constitutional authority merely by being connected. Outputs remain candidate knowledge and candidate engineering work until separately validated.

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
