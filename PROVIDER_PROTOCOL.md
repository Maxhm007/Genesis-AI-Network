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

## Built-in optional DeepSeek adapter

Genesis can add DeepSeek behind the same provider abstraction without replacing Qwen or changing the existing provider configuration. The adapter is disabled unless an operator supplies an API key at runtime:

```text
DEEPSEEK_API_KEY=<runtime-secret>
```

Optional settings:

```text
GENESIS_DEEPSEEK_MODEL=deepseek-v4-flash
GENESIS_DEEPSEEK_BASE_URL=https://api.deepseek.com
GENESIS_DEEPSEEK_TIMEOUT_SECONDS=90
GENESIS_DEEPSEEK_MAX_TOKENS=512
GENESIS_DEEPSEEK_THINKING=enabled
GENESIS_DEEPSEEK_REASONING_EFFORT=high
```

The default model is `deepseek-v4-flash`. The adapter uses DeepSeek's OpenAI-compatible `POST /chat/completions` API and declares reasoning, coding, research, planning and review capabilities. It does not store credentials in the repository.

Routing remains Genesis-owned. General `IntelligenceRouter` selection continues to preserve its existing Qwen preference when Qwen is available, while DeepSeek is an eligible fallback. Autonomous coding continues to obey the repository's existing coding-provider policy, which may prefer an eligible non-Qwen coder based on the current validated repair policy. In every case, tests, Security, review, independent validation and promotion gates remain unchanged.

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
