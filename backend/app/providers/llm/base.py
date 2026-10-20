"""LLM provider interfaces for optional clip reranking (PRD §5 FR-05, FR-11).

Honesty and safety contract:
- Providers are optional. The deterministic baseline scorer must work with no
  provider configured at all.
- API keys are secrets: they are never logged and never returned from any API.
  All log/error text passes through ``redact_secrets`` before storage.
- Transcript text is untrusted data. Providers only transport prompts; guards
  against instruction injection live in the ranker that builds the prompt and
  validates the response.
- No provider may supply authoritative cut timestamps. Ranking output is
  validated against known candidate IDs; timing stays in Python.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Callable

SECRET_MASK = "***REDACTED***"


def redact_secrets(text: str, secrets: list[str] | tuple[str, ...] | None) -> str:
    """Return ``text`` with every known secret replaced by a mask.

    Used before any message is logged or attached to an error record so that
    API keys can never leak into logs or API responses. Handles the empty-key
    case gracefully (no masking) and masks even partial appearances.
    """
    if not text:
        return text
    for secret in secrets or ():
        if secret and len(secret) >= 4 and secret in text:
            text = text.replace(secret, SECRET_MASK)
    return text


class LLMProviderError(RuntimeError):
    """Raised when a provider call fails (network, timeout, HTTP error).

    ``message`` MUST already be secret-redacted by the raiser; ``safe_detail``
    is bounded provider-agnostic detail (HTTP status, error kind) safe for API
    responses.
    """

    def __init__(self, message: str, safe_detail: str | None = None):
        super().__init__(message)
        self.message = message
        self.safe_detail = safe_detail


class LLMProviderTimeoutError(LLMProviderError):
    """Raised when the provider does not answer within the configured timeout."""


class LLMProvider(ABC):
    """Abstract transport for chat-completion style providers (PRD §5 FR-11).

    Implementations own retries, timeouts, and token limits. They never log
    raw prompts, raw responses, or credentials, and never return credentials.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable provider identifier (e.g. ``openai_compatible``)."""

    @abstractmethod
    def is_available(self) -> bool:
        """True when configuration/dependencies allow a call to be attempted."""

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        system_prompt: str,
        max_output_tokens: int,
        timeout_s: float,
        max_retries: int,
        cancel_event: asyncio.Event | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> str:
        """Return the model's raw text completion for one prompt.

        Args:
            prompt: User turn (built by the ranker; contains untrusted data).
            system_prompt: System turn (Laqta-owned instructions only).
            max_output_tokens: Hard upper bound on generated tokens.
            timeout_s: Per-attempt wall-clock timeout in seconds.
            max_retries: Additional attempts after the first failure.
            cancel_event: Cooperative cancellation flag.
            progress_callback: Optional stage reporter for honest progress.

        Raises:
            LLMProviderTimeoutError: attempts exhausted due to timeouts.
            LLMProviderError: attempts exhausted due to other failures.
        """
