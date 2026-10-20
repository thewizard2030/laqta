"""Tests for the OpenRouter LLM provider (core pipeline, stage s04).

Everything is mocked: no network access, no model, no real key. The tests
pin the fail-closed contract (no key -> no request), the request shape
(headers/payload), the honest error mapping (429 rate limit) and the live
free-model catalogue parsing.
"""

import json
from pathlib import Path

import httpx
import pytest

from qatta.core.config import QattaSettings
from qatta.core.pipeline import PipelineError
from qatta.core.schema import AtomicUtterance
from qatta.stages.s04_candidates.generator import format_utterance
from qatta.stages.s04_candidates.llm import (
    OPENROUTER_FREE_MODEL_IDS,
    OpenRouterProvider,
    WindowPayload,
    list_free_models,
    select_provider,
)

_HONEST_PROPOSAL = {
    "start_u_id": "U_0002",
    "end_u_id": "U_0005",
    "archetype": "STORY",
    "hook_remix": {"enabled": False, "hook_u_id": None, "ai_bridge_text": None},
    "broll": [],
    "pinned_comment_cta": "شكراً لكم",
    "curiosity_titles": ["عنوان أول", "عنوان ثاني", "عنوان ثالث"],
}


def _make_settings(tmp_path: Path, **overrides) -> QattaSettings:
    values = {
        "data_dir": tmp_path,
        "llm_provider": "openrouter",
        "allow_cloud_apis": True,
        "llm_openrouter_api_key": "sk-or-test",
    }
    values.update(overrides)
    return QattaSettings(**values)


def _window() -> WindowPayload:
    utterances = [
        AtomicUtterance(
            u_id=f"U_{i:04d}",
            start_ms=i * 5000,
            end_ms=i * 5000 + 3000,
            text=f"نص {i}",
            audio_rms_norm=0.5,
            pause_after_ms=0,
        )
        for i in range(1, 10)
    ]
    return WindowPayload(
        window_index=0,
        utterances=[format_utterance(u) for u in utterances],
    )


# ---------------------------------------------------------------------------
# Fail-closed gating
# ---------------------------------------------------------------------------


def test_openrouter_requires_cloud_opt_in(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path, allow_cloud_apis=False)

    with pytest.raises(PipelineError) as exc:
        select_provider(settings)

    assert "ALLOW_CLOUD_APIS" in str(exc.value)


def test_openrouter_requires_a_key(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path, llm_openrouter_api_key=None)

    with pytest.raises(PipelineError) as exc:
        select_provider(settings)

    assert "QATTA_LLM_OPENROUTER_API_KEY" in str(exc.value)


def test_openrouter_provider_constructor_refuses_empty_key() -> None:
    with pytest.raises(PipelineError) as exc:
        OpenRouterProvider(api_key="")

    assert "No request was sent" in str(exc.value)


# ---------------------------------------------------------------------------
# Provider selection + defaults
# ---------------------------------------------------------------------------


def test_select_provider_returns_openrouter(tmp_path: Path) -> None:
    provider = select_provider(_make_settings(tmp_path))
    assert provider.name == "openrouter"
    assert isinstance(provider, OpenRouterProvider)


def test_openrouter_defaults_follow_the_provider(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)

    # The generic LLM fields follow OpenRouter when the user left them at
    # the Ollama defaults, so one env var is enough to make it work.
    assert settings.llm_base_url == "https://openrouter.ai/api/v1"
    assert settings.llm_model == settings.llm_openrouter_model


def test_explicit_model_overrides_the_openrouter_default(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path, llm_model="my/free-model:free")

    assert settings.llm_model == "my/free-model:free"


# ---------------------------------------------------------------------------
# Request shape (mocked transport)
# ---------------------------------------------------------------------------


def test_openrouter_roundtrip_with_mock(tmp_path: Path) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        seen["referer"] = request.headers.get("HTTP-Referer")
        seen["title"] = request.headers.get("X-Title")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps({"candidates": [_HONEST_PROPOSAL]})}}
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenRouterProvider(
        api_key="sk-or-test",
        model="minimax/minimax-m3.1-flash:free",
        base_url="https://openrouter.test/api/v1",
        site_url="http://127.0.0.1:5173",
        app_title="Laqta",
        client=client,
    )

    result = provider.propose_candidates(_window())
    client.close()

    assert result.provider_name == "openrouter"
    assert result.proposals[0]["start_u_id"] == "U_0002"

    assert seen["url"] == "https://openrouter.test/api/v1/chat/completions"
    assert seen["auth"] == "Bearer sk-or-test"
    assert seen["referer"] == "http://127.0.0.1:5173"
    assert seen["title"] == "Laqta"

    body = seen["body"]
    assert body["model"] == "minimax/minimax-m3.1-flash:free"
    assert body["response_format"] == {"type": "json_object"}
    # Rule 3: the model only ever sees utterance lines, never raw timestamps
    # to output. The prompt carries the u_id lines produced by the stage.
    assert body["messages"][0]["role"] == "system"
    assert "NO timestamps" in body["messages"][0]["content"]


def test_openrouter_retries_without_json_mode_when_unsupported(
    tmp_path: Path,
) -> None:
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload)
        if "response_format" in payload:
            return httpx.Response(
                400,
                json={"error": {"message": "response_format is not supported by this model"}},
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps({"candidates": [_HONEST_PROPOSAL]})}}
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenRouterProvider(
        api_key="sk-or-test", base_url="https://openrouter.test/api/v1", client=client
    )
    result = provider.propose_candidates(_window())
    client.close()

    assert result.proposals
    assert len(calls) == 2
    assert "response_format" in calls[0]
    assert "response_format" not in calls[1]


# ---------------------------------------------------------------------------
# Honest error mapping
# ---------------------------------------------------------------------------


def test_rate_limit_is_reported_honestly(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={
                "error": {
                    "message": "Provider returned error",
                    "metadata": {"raw": "model is temporarily rate-limited upstream"},
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenRouterProvider(
        api_key="sk-or-test", base_url="https://openrouter.test/api/v1", client=client
    )
    with pytest.raises(PipelineError) as exc:
        provider.propose_candidates(_window())
    client.close()

    message = str(exc.value)
    assert "429" in message
    assert "rate-limited" in message
    # The failure must point at the local fallback, not pretend it worked.
    assert "deterministic local generator" in message


def test_error_body_never_leaks_the_api_key(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": {"message": "bad key sk-or-supersecretvalue"}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenRouterProvider(
        api_key="sk-or-supersecretvalue",
        base_url="https://openrouter.test/api/v1",
        client=client,
    )
    with pytest.raises(PipelineError) as exc:
        provider.propose_candidates(_window())
    client.close()

    message = str(exc.value)
    assert "sk-or-supersecretvalue" not in message
    assert "rejected the API key" in message


# ---------------------------------------------------------------------------
# Free-model catalogue
# ---------------------------------------------------------------------------


def test_list_free_models_filters_zero_priced_entries() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "vendor/paid-model",
                        "name": "Paid",
                        "pricing": {"prompt": "0.000003", "completion": "0.00001"},
                        "context_length": 1000,
                        "supported_parameters": ["response_format"],
                    },
                    {
                        "id": "vendor/free-model:free",
                        "name": "Free",
                        "pricing": {"prompt": "0", "completion": "0"},
                        "context_length": 64000,
                        "supported_parameters": ["response_format"],
                    },
                    {
                        "id": "vendor/free-no-json:free",
                        "name": "Free without JSON",
                        "pricing": {"prompt": "0", "completion": "0"},
                        "context_length": 8000,
                        "supported_parameters": [],
                    },
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    models = list_free_models(client=client)
    client.close()

    assert [m["id"] for m in models] == [
        "vendor/free-model:free",
        "vendor/free-no-json:free",
    ]
    assert models[0]["supports_json"] is True
    assert models[1]["supports_json"] is False


def test_list_free_models_reports_http_failures() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(PipelineError) as exc:
        list_free_models(client=client)
    client.close()

    assert "HTTP 503" in str(exc.value)


def test_curated_free_model_ids_are_zero_price_ids() -> None:
    assert OPENROUTER_FREE_MODEL_IDS
    for model_id in OPENROUTER_FREE_MODEL_IDS:
        assert model_id.endswith(":free"), model_id
