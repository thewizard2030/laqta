"""LLM providers for stage s04 (structured JSON candidate proposals).

Contract per the architectural rules (rule 3): the LLM NEVER receives raw
timestamps to output and NEVER decides ms boundaries. It receives
utterance lines keyed by ``u_id`` (with derived context metadata) and must
answer strictly with ``start_u_id`` / ``end_u_id`` spans; the pipeline
derives all real milliseconds from :class:`AtomicUtterance` rows. B-roll
cues are expressed as ``offset_sec`` RELATIVE TO THE CLIP START and are
clamped/converted to ``trigger_ms`` by this module — the LLM's job is
selection and description, not timing.

Providers:
- ``OllamaProvider``: LOCAL (default). POSTs to ``/api/chat`` with
  ``format="json"`` at ``llm_base_url`` (default 127.0.0.1:11434). No data
  leaves the machine except for the transcript text.
- ``GeminiProvider`` / ``OpenAICompatibleProvider``: CLOUD, fail-closed —
  both require ``QATTA_ALLOW_CLOUD_APIS=true`` AND their key
  (``QATTA_LLM_API_KEY``), otherwise they raise BEFORE any request.
- ``OpenRouterProvider``: CLOUD, fail-closed — one OpenAI-compatible gateway
  in front of many hosted models. Requires ``QATTA_ALLOW_CLOUD_APIS=true``
  AND ``QATTA_LLM_OPENROUTER_API_KEY``. Models whose id ends with ``:free``
  are offered at zero price but are rate limited upstream, so a 429 is an
  expected outcome that degrades to the deterministic local generator.

All providers speak one interface: ``propose_candidates(window) ->
list[dict]`` with validated raw dicts (later hardened into
``ClipCandidate`` objects by the stage). ``httpx.Client`` is injectable
for deterministic tests (``httpx.MockTransport``).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from qatta.core.pipeline import PipelineError

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)

_VALID_ARCHETYPES = ("STORY", "TACTICAL_INSIGHT", "HOT_TAKE")
_VALID_OVERLAYS = ("STOCK_VIDEO", "TEXT_CARD", "PUNCH_IN_ZOOM")

MAX_BRIDGE_TEXT_SEC = 2.0  # Arabic bridge text budget (~2s of speech)
MAX_BRIDGE_CHARS = 60


@dataclass(frozen=True)
class WindowPayload:
    """One sliding window of utterances handed to the provider."""

    window_index: int
    utterances: list[dict[str, Any]]  # already formatted lines + meta
    # utterances items: u_id, text, start_ms, end_ms, rms, pause_after_ms,
    # pitch_variance, silence_ratio, time_label


@dataclass(frozen=True)
class ProviderResult:
    """Raw proposals from one provider call, before hard validation."""

    proposals: list[dict[str, Any]]
    provider_name: str
    warnings: list[str] = field(default_factory=list)


class LLMProvider:
    """Protocol-ish base class; concrete providers subclass it."""

    name = "base"

    def propose_candidates(self, window: WindowPayload) -> ProviderResult:
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover - default no-op
        pass


# ---------------------------------------------------------------------------
# Shared system prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """أنت مساعد تحرير خبير في اختيار مقاطع يوتيوب شورتس
(Shorts) من محاضرات وبودكاست طويلة بالعربية (اللهجة المصرية) مع مصطلحات
تقنية إنجليزية (Arablish). سنعرض لك نافذة من جمل ذرية مرقمة. كل جملة
سطر واحد بصيغة:
[U_0104 | 06:52.3 - 06:56.8 | RMS:0.78 | PauseAfter:620ms] أكبر غلطة
عملناها في startup بودكاست

المطلوب منك اختيار أفضل المقاطع المرشحة لشورتس كامل مستقل (28-58 ثانية
غالباً) وفق قواعد صارمة:
1) استخدم فقط u_id الموجود في النافذة. لا تخترع أرقاماً ولا طوابع
   زمنية (milliseconds) أبداً — الطوابع الزمنية يحسبها النظام من الجمل.
2) صنّف كل مقطع archetype واحدة فقط: STORY أو TACTICAL_INSIGHT أو
   HOT_TAKE.
3) إن بدأ المقطع بسياق معلّق (جملة تابعة لسابقها)، قلّح start_u_id
   للجملة السابقة المناسبة داخل النافذة إن وُجدت.
4) بديل جسر (ai_bridge_text): جملة عربية قصيرة تعادل نحو ثانيتين
   (أقصى 60 حرفاً) تعيد بناء السياق للجمهور الغائب، مع hook_u_id من
   داخل المقطع نفسه.
5) اقترح 3-5 إشارات B-roll موزعة كل 5-7 ثوانٍ من بداية المقطع، بإزاحة
   offset_sec نسبية من بداية المقطع (ليست طوابع زمنية للمصدر) و
   overlay_type واحدة من: STOCK_VIDEO / TEXT_CARD / PUNCH_IN_ZOOM.
6) صُغ pinned_comment_cta وثلاثة عناوين فضول بالعربية curiosity_titles.

أجب بـ JSON فقط بالبنية:
{"candidates": [{"start_u_id": "U_0002", "end_u_id": "U_0009",
"archetype": "STORY",
  "hook_remix": {"enabled": false, "hook_u_id": null,
  "ai_bridge_text": null},
  "broll": [{"offset_sec": 1.5, "duration_sec": 2.0,
  "search_query": "...", "overlay_type": "STOCK_VIDEO"}],
  "pinned_comment_cta": "...", "curiosity_titles": ["...", "...",
  "..."]}]}


NO timestamps. NO milliseconds. u_id values only."""


def strip_code_fences(text: str) -> str:
    """Extract the JSON payload beneath any ```json fence."""
    match = _JSON_FENCE_RE.search(text)
    if match:
        return match.group(1)
    return text


def parse_llm_json(text: str) -> dict[str, Any]:
    """Parse the model's JSON answer into a dict (raising on garbage)."""
    candidates_json = strip_code_fences(text)
    try:
        data = json.loads(candidates_json)
    except json.JSONDecodeError as e:
        raise PipelineError(
            "LLM response was not parseable JSON (fenced or bare). "
            f"Payload head: {candidates_json[:200]!r}"
        ) from e
    if not isinstance(data, dict):
        raise PipelineError("LLM response must be a JSON object with a 'candidates' key.")
    if "candidates" not in data or not isinstance(data["candidates"], list):
        raise PipelineError("LLM JSON missing 'candidates' list.")
    return data


def validate_proposal(proposal: dict[str, Any], u_index: dict[str, Any]) -> dict[str, Any]:
    """Validate ONE raw LLM proposal against the window's u_ids.

    Returns a normalized dict. Raises PipelineError with the reason when
    the proposal is unusable so callers can skip it with a warning.
    """
    start_u = proposal.get("start_u_id")
    end_u = proposal.get("end_u_id")
    archetype = proposal.get("archetype")
    if not isinstance(start_u, str) or not isinstance(end_u, str):
        raise PipelineError("proposal missing u_id strings")
    if start_u not in u_index or end_u not in u_index:
        raise PipelineError(f"u_ids outside window: {start_u!r} -> {end_u!r}")
    start = u_index[start_u]
    end = u_index[end_u]
    if start["ordinal"] >= end["ordinal"]:
        raise PipelineError(f"span inverted or single-utterance: {start_u}->{end_u}")
    if archetype not in _VALID_ARCHETYPES:
        raise PipelineError(f"unknown archetype: {archetype!r}")

    hook = proposal.get("hook_remix") or {}
    hook_u_id = hook.get("hook_u_id")
    bridge = hook.get("ai_bridge_text")
    enabled = bool(hook.get("enabled"))
    if enabled and not (hook_u_id in u_index and bridge):
        raise PipelineError("enabled hook_remix without hook_u_id/bridge")
    hook_u_id = hook_u_id if hook_u_id in u_index else None
    bridge_text = None
    if isinstance(bridge, str) and bridge.strip():
        bridge_text = bridge.strip()[:MAX_BRIDGE_CHARS]

    broll_raw = proposal.get("broll") or []
    if not isinstance(broll_raw, list):
        broll_raw = []
    broll: list[dict[str, Any]] = []
    clip_dur_sec = (end["end_ms"] - start["start_ms"]) / 1000.0
    for cue in broll_raw[:6]:
        if not isinstance(cue, dict):
            continue
        overlay = cue.get("overlay_type")
        if overlay not in _VALID_OVERLAYS:
            continue
        try:
            offset = float(cue.get("offset_sec", 0.0))
            dur = float(cue.get("duration_sec", 2.0))
        except (TypeError, ValueError):
            continue
        # Clamp into the clip: relative sec -> absolute ms by the SYSTEM.
        offset = min(max(offset, 0.0), max(0.0, clip_dur_sec - 0.5))
        dur = min(max(dur, 0.5), 5.0)
        search = (cue.get("search_query") or "").strip()
        if not search:
            continue
        broll.append(
            {
                "offset_sec": offset,
                "duration_sec": dur,
                "search_query": search,
                "overlay_type": overlay,
            }
        )

    cta = proposal.get("pinned_comment_cta")
    titles_raw = proposal.get("curiosity_titles") or []
    titles = [t.strip() for t in titles_raw if isinstance(t, str) and t.strip()][:3]

    return {
        "start_u_id": start_u,
        "end_u_id": end_u,
        "archetype": archetype,
        "hook_remix": {
            "enabled": enabled,
            "hook_u_id": hook_u_id,
            "ai_bridge_text": bridge_text,
            "context_preserved": bool(hook.get("context_preserved", True)),
        },
        "broll": broll,
        "pinned_comment_cta": (cta.strip() if isinstance(cta, str) and cta.strip() else None),
        "curiosity_titles": titles,
    }


def _post_chat_json(client, url: str, payload: dict[str, Any], headers: dict[str, str]) -> str:
    """One bounded POST; returns the assistant text content."""
    try:
        response = client.post(url, json=payload, headers=headers)
    except Exception as e:
        raise PipelineError(f"LLM provider request failed ({url}): {type(e).__name__}: {e}") from e
    if response.status_code != 200:
        raise PipelineError(
            f"LLM provider {url} returned {response.status_code}: {(response.text or '')[:300]}"
        )
    return response.text


class OllamaProvider(LLMProvider):
    """LOCAL provider: Ollama chat API with forced JSON output."""

    name = "ollama"

    def __init__(
        self,
        model: str,
        base_url: str = "http://127.0.0.1:11434/v1",
        timeout_seconds: float = 30.0,
        client=None,
    ):
        self.model = model
        # Ollama's native API lives at the root (not /v1); keep both
        # workable because the config default shares the OpenAI url.
        self.base_url = base_url.rstrip("/").removesuffix("/v1")
        self.timeout_seconds = timeout_seconds
        self._client = client

    def propose_candidates(self, window: WindowPayload) -> ProviderResult:
        import httpx

        client = self._client or httpx.Client(timeout=self.timeout_seconds)
        owned = self._client is None
        prompt_lines = "\n".join(u.get("line", "") for u in window.utterances)
        payload = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": prompt_lines,
                },
            ],
            "options": {"temperature": 0.2},
        }
        try:
            text = _post_chat_json(client, f"{self.base_url}/api/chat", payload, {})
            data = json.loads(text)
        finally:
            if owned:
                client.close()
        content = data.get("message", {}).get("content", "") if isinstance(data, dict) else ""
        parsed = parse_llm_json(content)
        return ProviderResult(proposals=parsed["candidates"], provider_name=self.name)


class GeminiProvider(LLMProvider):
    """CLOUD provider (fail-closed): Google Generative Language API."""

    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        timeout_seconds: float = 30.0,
        client=None,
    ):
        if not api_key:
            raise PipelineError("GeminiProvider requires QATTA_LLM_API_KEY. No request was sent.")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._client = client

    def propose_candidates(self, window: WindowPayload) -> ProviderResult:
        import httpx

        prompt_lines = "\n".join(u.get("line", "") for u in window.utterances)
        payload = {
            "contents": [{"parts": [{"text": prompt_lines}]}],
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.2,
            },
        }
        client = self._client or httpx.Client(timeout=self.timeout_seconds)
        owned = self._client is None
        try:
            text = _post_chat_json(
                client,
                f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}",
                payload,
                {},
            )
            data = json.loads(text)
        finally:
            if owned:
                client.close()
        # The response carries candidates[0].content.parts[0].text.
        try:
            content = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as e:
            raise PipelineError(
                f"Gemini returned an unexpected response shape: {json.dumps(data)[:300]}"
            ) from e
        parsed = parse_llm_json(content)
        return ProviderResult(proposals=parsed["candidates"], provider_name=self.name)


class OpenAICompatibleProvider(LLMProvider):
    """CLOUD provider (fail-closed): any OpenAI /chat/completions API."""

    name = "openai_compatible"

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 30.0,
        client=None,
    ):
        if not api_key:
            raise PipelineError(
                "OpenAICompatibleProvider requires QATTA_LLM_API_KEY. No request was sent."
            )
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._client = client

    def propose_candidates(self, window: WindowPayload) -> ProviderResult:
        import httpx

        prompt_lines = "\n".join(u.get("line", "") for u in window.utterances)
        payload = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt_lines},
            ],
        }
        client = self._client or httpx.Client(timeout=self.timeout_seconds)
        owned = self._client is None
        try:
            text = _post_chat_json(
                client,
                f"{self.base_url}/chat/completions",
                payload,
                {"Authorization": f"Bearer {self.api_key}"},
            )
            data = json.loads(text)
        finally:
            if owned:
                client.close()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise PipelineError(
                "OpenAI-compatible provider returned an unexpected "
                f"response shape: {json.dumps(data)[:300]}"
            ) from e
        parsed = parse_llm_json(content)
        return ProviderResult(proposals=parsed["candidates"], provider_name=self.name)


def require_cloud_llm_permission(provider_name: str, settings) -> None:
    """Fail-closed gate for CLOUD LLM providers (Gemini/OpenAI/OpenRouter)."""
    if provider_name == "ollama":
        return
    if not settings.allow_cloud_apis:
        raise PipelineError(
            f"Cloud LLM provider '{provider_name}' requires explicit "
            "opt-in (QATTA_ALLOW_CLOUD_APIS=true). Transcript text "
            "would leave the device; nothing was sent."
        )


# ---------------------------------------------------------------------------
# OpenRouter (CLOUD, fail-closed) — one gateway, many models, many free ones
# ---------------------------------------------------------------------------

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

# Curated snapshot of the zero-price models that were observed to support
# JSON output (``response_format``) when the provider was implemented
# (2026-10-19). OpenRouter rotates its free pool, so treat this as a
# starting point, not a guarantee — ``list_free_models`` queries the live
# catalog. A model that is rate limited (HTTP 429) is NOT an error state:
# the caller falls back to the deterministic local generator.
OPENROUTER_FREE_MODEL_IDS: tuple[str, ...] = (
    "minimax/minimax-m3.1-flash:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "nvidia/nemotron-3.5-super-vl:free",
    "xingchen-agi/xing4.0-29b-a4b:free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "liquid/lfm-2.5-2.6b:free",
    "dots-studio/dots-3-note-preview:free",
)

# Bounded limits for the public catalog lookup (no API key required).
_FREE_MODELS_TIMEOUT_SECONDS = 15.0
_FREE_MODELS_MAX_BYTES = 2_000_000


def list_free_models(
    client=None,
    timeout_seconds: float = _FREE_MODELS_TIMEOUT_SECONDS,
) -> list[dict[str, Any]]:
    """Return the live catalog of zero-price OpenRouter models.

    Uses the public ``GET /api/v1/models`` endpoint (no key, no transcript
    data). A model qualifies when its prompt AND completion pricing are
    zero. The result is sorted by id and bounded; network failures raise
    ``PipelineError`` so callers can report them honestly.
    """
    import httpx

    owned = client is None
    http_client = client or httpx.Client(timeout=timeout_seconds)
    try:
        response = http_client.get(OPENROUTER_MODELS_URL)
    except Exception as e:  # network error -> honest failure
        raise PipelineError(
            f"OpenRouter model catalog request failed: {type(e).__name__}: {e}"
        ) from e
    finally:
        if owned:
            http_client.close()

    if response.status_code != 200:
        raise PipelineError(f"OpenRouter model catalog returned HTTP {response.status_code}.")
    if len(response.content) > _FREE_MODELS_MAX_BYTES:
        raise PipelineError("OpenRouter model catalog response was too large.")

    try:
        payload = json.loads(response.text)
        models = payload["data"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise PipelineError("OpenRouter model catalog had an unexpected shape.") from e
    if not isinstance(models, list):
        raise PipelineError("OpenRouter model catalog 'data' is not a list.")

    free: list[dict[str, Any]] = []
    for model in models:
        if not isinstance(model, dict):
            continue
        pricing = model.get("pricing") or {}
        if pricing.get("prompt") not in ("0", "0.0"):
            continue
        if pricing.get("completion") not in ("0", "0.0"):
            continue
        free.append(
            {
                "id": model.get("id"),
                "name": model.get("name"),
                "context_length": model.get("context_length"),
                "supports_json": "response_format" in (model.get("supported_parameters") or []),
            }
        )
    free.sort(key=lambda m: str(m.get("id") or ""))
    return free


class OpenRouterProvider(LLMProvider):
    """CLOUD provider (fail-closed): OpenRouter's OpenAI-compatible gateway.

    OpenRouter proxies many hosted models behind
    ``POST {base_url}/chat/completions``. Model ids ending in ``:free`` are
    zero-price but rate limited upstream, so HTTP 429 is reported as a clear,
    actionable error and the caller degrades to the deterministic generator.

    Honesty/safety contract (inherited from ``LLMProvider``):
    - The API key is a secret: it travels only in the ``Authorization``
      header and never appears in a log line, error message or manifest.
    - The model NEVER sees or returns timestamps (rule 3): it answers with
      ``u_id`` spans only.
    - Nothing is sent when the key is missing (fail-closed).
    """

    name = "openrouter"

    def __init__(
        self,
        api_key: str,
        model: str = "minimax/minimax-m3.1-flash:free",
        base_url: str = OPENROUTER_BASE_URL,
        timeout_seconds: float = 30.0,
        site_url: str = "http://127.0.0.1:5173",
        app_title: str = "Laqta",
        client=None,
    ):
        if not api_key:
            raise PipelineError(
                "OpenRouterProvider requires QATTA_LLM_OPENROUTER_API_KEY. No request was sent."
            )
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        # Attribution headers (not secrets) used by OpenRouter's dashboard.
        self.site_url = site_url
        self.app_title = app_title
        self._client = client

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": self.site_url,
            "X-Title": self.app_title,
        }

    def propose_candidates(self, window: WindowPayload) -> ProviderResult:
        prompt_lines = "\n".join(u.get("line", "") for u in window.utterances)
        base_payload = {
            "model": self.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt_lines},
            ],
        }
        # Ask for strict JSON first. Not every free model advertises
        # ``response_format``; when the gateway rejects it we retry once
        # without it (the prompt itself demands JSON only and the parser
        # also accepts fenced JSON).
        for payload in (
            {**base_payload, "response_format": {"type": "json_object"}},
            base_payload,
        ):
            response = self._post(payload)
            if response.status_code == 200:
                return self._parse(response)
            if response.status_code == 400 and "response_format" in payload:
                continue  # retry without JSON mode
            self._raise_for_status(response)
        raise PipelineError("OpenRouter rejected the request payload.")

    def _post(self, payload: dict[str, Any]):
        import httpx

        client = self._client or httpx.Client(timeout=self.timeout_seconds)
        owned = self._client is None
        try:
            return client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
            )
        except Exception as e:
            raise PipelineError(f"OpenRouter request failed: {type(e).__name__}: {e}") from e
        finally:
            if owned:
                client.close()

    def _parse(self, response) -> ProviderResult:
        try:
            data = json.loads(response.text)
        except json.JSONDecodeError as e:
            raise PipelineError("OpenRouter returned a non-JSON response body.") from e
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise PipelineError(
                f"OpenRouter returned an unexpected response shape: {json.dumps(data)[:300]}"
            ) from e
        parsed = parse_llm_json(content)
        return ProviderResult(proposals=parsed["candidates"], provider_name=self.name)

    def _raise_for_status(self, response) -> None:
        """Map an OpenRouter error body to an honest, actionable message.

        The body is provider-controlled: it is bounded and the API key is
        stripped before the text is used in an error.
        """
        detail = ""
        try:
            body = response.json()
            error = body.get("error") if isinstance(body, dict) else None
            if isinstance(error, dict):
                detail = str(error.get("message") or "")[:300]
                metadata = error.get("metadata")
                if isinstance(metadata, dict) and metadata.get("raw"):
                    detail = f"{detail} {str(metadata['raw'])[:200]}".strip()
        except Exception:
            detail = (response.text or "")[:300]
        # Never let the key leak through an error body.
        detail = detail.replace(self.api_key, "***")

        if response.status_code == 429:
            raise PipelineError(
                "OpenRouter rate-limited this request (HTTP 429). Free "
                "models share a limited upstream pool — retry later or pick "
                "another free model; the deterministic local generator "
                f"remains available. Detail: {detail}"
            )
        if response.status_code in (401, 403):
            raise PipelineError(
                "OpenRouter rejected the API key (HTTP "
                f"{response.status_code}). Check QATTA_LLM_OPENROUTER_API_KEY."
            )
        raise PipelineError(f"OpenRouter returned HTTP {response.status_code}: {detail}")


def select_provider(settings, client=None) -> LLMProvider:
    """Instantiate the configured provider (fail-closed for cloud)."""
    provider_name = settings.llm_provider
    require_cloud_llm_permission(provider_name, settings)
    if provider_name == "ollama":
        return OllamaProvider(
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            timeout_seconds=settings.llm_timeout_seconds,
            client=client,
        )
    if provider_name == "gemini":
        if not settings.llm_api_key:
            raise PipelineError("gemini provider selected but QATTA_LLM_API_KEY is empty.")
        return GeminiProvider(
            api_key=settings.llm_api_key,
            model=settings.llm_model or "gemini-2.0-flash",
            timeout_seconds=settings.llm_timeout_seconds,
            client=client,
        )
    if provider_name == "openrouter":
        if not settings.llm_openrouter_api_key:
            raise PipelineError(
                "openrouter provider selected but QATTA_LLM_OPENROUTER_API_KEY is empty."
            )
        return OpenRouterProvider(
            api_key=settings.llm_openrouter_api_key,
            model=settings.llm_model or "minimax/minimax-m3.1-flash:free",
            base_url=settings.llm_base_url or OPENROUTER_BASE_URL,
            timeout_seconds=settings.llm_timeout_seconds,
            site_url=settings.llm_openrouter_site_url,
            app_title=settings.llm_openrouter_app_title,
            client=client,
        )
    if not settings.llm_api_key:
        raise PipelineError("openai_compatible selected but QATTA_LLM_API_KEY is empty.")
    return OpenAICompatibleProvider(
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        base_url=settings.llm_base_url or "https://api.openai.com/v1",
        timeout_seconds=settings.llm_timeout_seconds,
        client=client,
    )
