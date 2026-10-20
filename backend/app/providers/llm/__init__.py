"""LLM provider adapters for candidate ranking (PRD §5 FR-05, FR-11).

Exposes:
- ``LLMProvider``: abstract transport for chat-completion providers.
- ``OpenAICompatibleProvider``: adapter for user-run LOCAL servers
  (Ollama/LM Studio/llama.cpp/vLLM). Secrets are redacted from logs and never
  returned from APIs; the API key travels only in the Authorization header.
- ``OpenRouterProvider``: HOSTED adapter for OpenRouter's OpenAI-compatible
  gateway (zero-price ``:free`` models included). It is a separate, explicit
  opt-in adapter because transcript text leaves the device (PRD §9).
"""

from app.providers.llm.base import (
    LLMProvider,
    LLMProviderError,
    LLMProviderTimeoutError,
    redact_secrets,
)
from app.providers.llm.openai_compatible import OpenAICompatibleProvider
from app.providers.llm.openrouter import (
    DEFAULT_BASE_URL as OPENROUTER_BASE_URL,
)
from app.providers.llm.openrouter import (
    FREE_MODEL_IDS as OPENROUTER_FREE_MODEL_IDS,
)
from app.providers.llm.openrouter import (
    OpenRouterProvider,
)

__all__ = [
    "LLMProvider",
    "LLMProviderError",
    "LLMProviderTimeoutError",
    "OpenAICompatibleProvider",
    "OpenRouterProvider",
    "OPENROUTER_BASE_URL",
    "OPENROUTER_FREE_MODEL_IDS",
    "redact_secrets",
]
