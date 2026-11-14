# LLM Providers

## Overview
LLM provider abstraction layer supporting local OpenAI-compatible endpoints (Ollama, LM Studio) and hosted OpenRouter with credential masking and timeout controls.

## Interface
- app.providers.llm.base:LLMProvider(ABC)
- app.providers.llm.base:LLMProviderError
- app.providers.llm.base:LLMProviderTimeoutError
- app.providers.llm.base:redact_secrets(text: str, secrets: list[str] | tuple[str, ...] | None) -> str
- app.providers.llm.base:SECRET_MASK: str = '***REDACTED***'
- app.providers.llm.openai_compatible:OpenAICompatibleProvider
- app.providers.llm.openai_compatible:DEFAULT_BASE_URL: str = 'http://127.0.0.1:11434/v1'
- app.providers.llm.openai_compatible:DEFAULT_MODEL: str = 'qwen2.5:7b-instruct'
- app.providers.llm.openrouter:OpenRouterProvider
- app.providers.llm.openrouter:DEFAULT_BASE_URL: str = 'https://openrouter.ai/api/v1'
- app.providers.llm.openrouter:FREE_MODEL_IDS: tuple[str, ...]

## Invariants
- Secret redaction: API keys are masked by redact_secrets before appearing in logs or error messages [base.py:redact_secrets]
- Fail-closed hosted provider: OpenRouter requires explicit opt-in (settings.ALLOW_CLOUD_APIS=true) and an API key; local OpenAI-compatible defaults to 127.0.0.1 loopback [openrouter.py, openai_compatible.py]
- Defensive request limits: prompt length capped to 200,000 chars, output capped to 4,000 tokens, retries capped to 3, and timeout bounded to 120s [openai_compatible.py, openrouter.py]

## Side Effects
- Outbound HTTP POST requests to local server (Ollama) or external API (OpenRouter) via httpx.AsyncClient [openai_compatible.py:complete, openrouter.py:complete]

## Verification
- Run: `pytest backend/tests`
