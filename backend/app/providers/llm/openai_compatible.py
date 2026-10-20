"""OpenAI-compatible chat-completions adapter for LOCAL tools (PRD §5 FR-11).

Intended endpoints: Ollama, LM Studio, llama.cpp server, vLLM, text-generation-
webui — anything exposing ``POST {base_url}/v1/chat/completions`` (or a base
URL that already includes ``/v1``).

Scope and honesty:
- This adapter is for user-run local servers. A hosted provider adapter may be
  added later; it would be a separate class and must be opt-in with UI
  disclosure that transcript text leaves the device (FR-11, PRD §9). Nothing
  here sends data anywhere except the user-configured ``base_url``.
- The API key is optional (many local servers require none). It is never
  logged, never returned, and redacted from every error string.
- Retries are bounded with fixed-style backoff; timeouts are enforced with
  ``asyncio.timeout``; output tokens are capped per request. Cancellation is
  cooperative via ``cancel_event``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from app.providers.llm.base import (
    LLMProvider,
    LLMProviderError,
    LLMProviderTimeoutError,
    redact_secrets,
)

logger = logging.getLogger("qatta.llm")

# Bounded hard limits, independent of caller configuration (defense in depth).
MAX_PROMPT_CHARS = 200_000
HARD_MAX_OUTPUT_TOKENS = 4_000
HARD_MAX_RETRIES = 3
HARD_MAX_TIMEOUT_S = 120.0
_RETRY_BACKOFF_S = 0.5

# Default base URL points at a user-run local server on loopback only.
DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"  # Ollama default
DEFAULT_MODEL = "qwen2.5:7b-instruct"


class OpenAICompatibleProvider(LLMProvider):
    """Adapter for any OpenAI-compatible chat-completions HTTP endpoint.

    Configured via settings: ``QATTA_LLM_BASE_URL`` (must be http(s)),
    ``QATTA_LLM_API_KEY`` (optional secret), ``QATTA_LLM_MODEL``.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model
        # Kept only to be sent in the Authorization header; never formatted
        # into any log line or error message unmasked.
        self._api_key = api_key or None

    @property
    def name(self) -> str:
        return "openai_compatible"

    @property
    def endpoint(self) -> str:
        """Public, secret-free endpoint description safe for logs/APIs."""
        return self._base_url

    def is_available(self) -> bool:
        try:
            import httpx  # noqa: F401
        except ImportError:
            return False
        return bool(self._base_url) and self._base_url.startswith(("http://", "https://"))

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        # The key travels only in the header. base_url/model remain loggable.
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

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
        if not self.is_available():
            raise LLMProviderError(
                "LLM provider is not available (missing httpx or invalid base URL).",
                safe_detail="provider_unavailable",
            )

        # Clamp caller-supplied limits to hard, documented caps.
        timeout_s = min(max(timeout_s, 1.0), HARD_MAX_TIMEOUT_S)
        max_retries = min(max(int(max_retries), 0), HARD_MAX_RETRIES)
        max_tokens = min(max(int(max_output_tokens), 16), HARD_MAX_OUTPUT_TOKENS)
        if len(prompt) > MAX_PROMPT_CHARS:
            raise LLMProviderError(
                f"Prompt exceeds bounded size ({len(prompt)} > {MAX_PROMPT_CHARS} chars).",
                safe_detail="prompt_too_large",
            )

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.0,  # deterministic-ish ranking output
            "stream": False,
        }

        last_error: Exception | None = None
        for attempt in range(1 + max_retries):
            if cancel_event is not None and cancel_event.is_set():
                raise LLMProviderError("Cancelled before provider call.", "cancelled")
            try:
                if progress_callback:
                    progress_callback(f"attempt_{attempt + 1}")
                return await self._post_once(payload, timeout_s, cancel_event)
            except (TimeoutError, LLMProviderTimeoutError) as e:
                last_error = e
                reason = "timeout"
            except LLMProviderError as e:
                # Non-timeout provider failures (HTTP 4xx/5xx, malformed HTTP,
                # connection errors) are retried too, but boundedly.
                last_error = e
                reason = "provider_error"
            if attempt < max_retries:
                await asyncio.sleep(_RETRY_BACKOFF_S * (attempt + 1))

        message = (
            f"LLM provider '{self.name}' failed after {1 + max_retries} attempt(s) "
            f"({reason}). Model: {self._model}."
        )
        if isinstance(last_error, LLMProviderTimeoutError):
            raise LLMProviderTimeoutError(
                redact_secrets(message, [self._api_key]), safe_detail="timeout"
            ) from last_error
        raise LLMProviderError(
            redact_secrets(message, [self._api_key]), safe_detail="provider_error"
        ) from last_error

    async def _post_once(
        self,
        payload: dict,
        timeout_s: float,
        cancel_event: asyncio.Event | None,
    ) -> str:
        """One HTTP attempt. Raises TimeoutError or LLMProviderError."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s)) as client:
                if cancel_event is not None:
                    # Poll cancellation while the request is in flight.
                    request_task = asyncio.create_task(
                        client.post(
                            f"{self._base_url}/chat/completions",
                            json=payload,
                            headers=self._headers(),
                        )
                    )
                    cancel_task = asyncio.create_task(_wait_cancelled(cancel_event))
                    done, pending = await asyncio.wait(
                        {request_task, cancel_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in pending:
                        task.cancel()
                    if cancel_task in done:
                        raise LLMProviderError("Cancelled during provider call.", "cancelled")
                    response = await request_task  # already done; re-raises errors
                else:
                    response = await client.post(
                        f"{self._base_url}/chat/completions",
                        json=payload,
                        headers=self._headers(),
                    )
        except (httpx.TimeoutException, TimeoutError) as e:
            raise TimeoutError(f"Provider request timed out after {timeout_s:.0f}s.") from e
        except (httpx.HTTPError, OSError) as e:
            # str(e) may embed the URL but never the API key (header-only).
            raise LLMProviderError(
                redact_secrets(f"Provider request failed: {e}", [self._api_key]),
                safe_detail="request_failed",
            ) from e

        if response.status_code != 200:
            # Body is provider-controlled; never forwarded unredacted/unbounded.
            raise LLMProviderError(
                redact_secrets(f"Provider returned HTTP {response.status_code}.", [self._api_key]),
                safe_detail=f"http_{response.status_code}",
            )

        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("completion content is not a string")
        except (KeyError, IndexError, TypeError, ValueError) as e:
            raise LLMProviderError(
                "Provider response had no usable completion content.",
                safe_detail="malformed_response",
            ) from e
        return content

    def describe_config(self) -> dict[str, str | None]:
        """Secret-free configuration summary for capabilities/UI disclosure."""
        return {
            "name": self.name,
            "base_url": self._base_url,
            "model": self._model,
            "api_key_configured": self._api_key is not None,  # never the key itself
        }


async def _wait_cancelled(cancel_event: asyncio.Event) -> None:
    await cancel_event.wait()
