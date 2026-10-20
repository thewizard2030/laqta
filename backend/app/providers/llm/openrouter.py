"""OpenRouter provider for the optional LLM reranker (PRD §5 FR-11).

OpenRouter proxies many hosted models behind one OpenAI-compatible API
(``https://openrouter.ai/api/v1``). Model ids ending in ``:free`` are offered
at zero price; the free pool is shared and rate limited upstream, so an HTTP
429 is an EXPECTED outcome rather than a bug.

Scope and honesty:
- HOSTED provider: transcript text leaves the device. The caller must have
  the explicit hosted opt-in (``QATTA_LLM_HOSTED_OPT_IN``) enabled; the
  router in ``app/api/routes/candidates.py`` refuses a non-loopback endpoint
  without it, so this class never bypasses that gate.
- The API key is a secret: it travels only in the ``Authorization`` header,
  is never logged, never returned, and is stripped from every error string.
- The key is NOT persisted anywhere; it is read from the environment.
"""

from __future__ import annotations

from app.providers.llm.openai_compatible import OpenAICompatibleProvider

# Public, secret-free defaults.
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

# Curated snapshot of zero-price models that advertised JSON output when the
# provider was implemented (2026-10-19). OpenRouter rotates its free pool;
# treat this as a starting point, not a guarantee.
FREE_MODEL_IDS: tuple[str, ...] = (
    "minimax/minimax-m3.1-flash:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "nvidia/nemotron-3.5-super-vl:free",
    "xingchen-agi/xing4.0-29b-a4b:free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "liquid/lfm-2.5-2.6b:free",
    "dots-studio/dots-3-note-preview:free",
)

DEFAULT_MODEL = FREE_MODEL_IDS[0]


class OpenRouterProvider(OpenAICompatibleProvider):
    """OpenAI-compatible adapter pointed at OpenRouter.

    Differences from the generic local adapter:
    - the provider identifier is ``openrouter`` (so logs and the UI can say
      which service is actually used),
    - OpenRouter's attribution headers (``HTTP-Referer`` / ``X-Title``) are
      sent; they are public app metadata, not secrets,
    - the default model is a zero-price model.
    """

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        site_url: str = "http://127.0.0.1:5173",
        app_title: str = "Laqta",
    ):
        super().__init__(base_url=base_url, model=model, api_key=api_key)
        self._site_url = site_url
        self._app_title = app_title

    @property
    def name(self) -> str:
        return "openrouter"

    def _headers(self) -> dict[str, str]:
        headers = super()._headers()
        headers["HTTP-Referer"] = self._site_url
        headers["X-Title"] = self._app_title
        return headers

    def describe_config(self) -> dict[str, str | None]:
        """Secret-free configuration summary for capabilities/UI disclosure."""
        return {
            "name": self.name,
            "base_url": self.endpoint,
            "model": self._model,
            "api_key_configured": self._api_key is not None,  # never the key
            "hosted": True,
        }
