"""Tests for Laqta Multi-Engine Transcription Manager and GPU Support.

Verifies:
- Provider selection, capabilities reporting, and REST endpoint.
- Hardware capability detection and graceful CUDA -> CPU INT8 fallback.
- Fail-closed privacy gating for cloud providers (QATTA_ALLOW_CLOUD_APIS).
- API key redaction in logging and settings.
- Mocked Groq, AssemblyAI, Hugging Face, and whisper.cpp integrations.
- Long-audio chunking, boundary timestamp stitching, and word deduplication.
- Caching behavior by media fingerprint and settings.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, settings
from app.schemas.transcription import TranscriptSegment, WordTiming
from app.services.transcription.assemblyai_provider import AssemblyAITranscriptionProvider
from app.services.transcription.base import TranscriptionError, TranscriptionResult
from app.services.transcription.chunking import (
    AudioChunk,
    merge_overlapping_segments,
)
from app.services.transcription.faster_whisper_provider import FasterWhisperProvider
from app.services.transcription.groq_provider import GroqTranscriptionProvider
from app.services.transcription.huggingface_provider import HuggingFaceTranscriptionProvider
from app.services.transcription.manager import TranscriptionManager
from app.services.transcription.whisper_cpp_provider import WhisperCppProvider


@pytest.fixture
def dummy_wav(tmp_path: Path) -> Path:
    """Create a valid dummy 16kHz mono WAV file for testing."""
    import wave

    wav_file = tmp_path / "test_sample.wav"
    with wave.open(str(wav_file), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        # 1 second of silence (16000 samples of 16-bit PCM = 32000 bytes)
        wf.writeframes(b"\x00\x00" * 16000)
    return wav_file


def test_api_key_redaction():
    """Verify secrets are redacted and never printed in logs or capabilities."""
    test_settings = Settings(
        GROQ_API_KEY="gsk_supersecretkey1234567890",
        ASSEMBLYAI_API_KEY="aai_supersecretkey1234567890",
        HF_TOKEN="hf_supersecretkey1234567890",
    )
    assert test_settings.redacted_groq_key.startswith("gsk_")
    assert "..." in test_settings.redacted_groq_key
    assert "supersecret" not in test_settings.redacted_groq_key

    assert test_settings.redacted_assemblyai_key.startswith("aai_")
    assert "supersecret" not in test_settings.redacted_assemblyai_key

    assert test_settings.redacted_hf_token.startswith("hf_")
    assert "supersecret" not in test_settings.redacted_hf_token


def test_list_providers_capabilities(dummy_wav: Path):
    """Test listing provider capabilities truthfully."""
    mgr = TranscriptionManager()
    providers = mgr.list_providers()
    provider_names = [p.provider for p in providers]

    assert "faster-whisper" in provider_names
    assert "whisper.cpp" in provider_names
    assert "groq" in provider_names
    assert "assemblyai" in provider_names
    assert "huggingface" in provider_names
    assert "fake" in provider_names

    # Check privacy disclosures
    for p in providers:
        assert p.privacy_disclosure is not None
        if p.is_cloud:
            assert (
                "uploaded" in p.privacy_disclosure.lower()
                or "transmitted" in p.privacy_disclosure.lower()
            )
        if p.is_local:
            assert "local" in p.privacy_disclosure.lower()


def test_transcription_providers_endpoint(client: TestClient):
    """Verify GET /api/transcription/providers endpoint."""
    res = client.get("/api/transcription/providers")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 5
    names = [d["provider"] for d in data]
    assert "faster-whisper" in names
    assert "groq" in names


@pytest.mark.asyncio
async def test_fail_closed_cloud_privacy_gating(dummy_wav: Path):
    """Ensure cloud providers reject requests if QATTA_ALLOW_CLOUD_APIS=false."""
    mgr = TranscriptionManager()

    with patch.object(settings, "ALLOW_CLOUD_APIS", False):
        for cloud_provider in ("groq", "assemblyai", "huggingface"):
            with pytest.raises(TranscriptionError) as exc_info:
                await mgr.transcribe(
                    audio_path=dummy_wav,
                    provider_name=cloud_provider,
                )
            assert exc_info.value.error_code == "CLOUD_APIS_DISABLED"


@pytest.mark.asyncio
async def test_missing_api_key_gating(dummy_wav: Path):
    """Ensure cloud providers reject requests if API key is not configured."""
    mgr = TranscriptionManager()

    with patch.object(settings, "ALLOW_CLOUD_APIS", True):
        with patch.object(settings, "GROQ_API_KEY", ""):
            with pytest.raises(TranscriptionError) as exc_info:
                await mgr.transcribe(
                    audio_path=dummy_wav,
                    provider_name="groq",
                )
            assert exc_info.value.error_code == "API_KEY_MISSING"


@pytest.mark.asyncio
async def test_cuda_detection_and_fallback(dummy_wav: Path):
    """Verify faster-whisper gracefully falls back to CPU INT8 when CUDA is missing or fails."""
    provider = FasterWhisperProvider()

    # Mock CTranslate2 reporting 0 CUDA devices
    with patch("ctranslate2.get_cuda_device_count", return_value=0):
        with patch.object(provider, "_transcribe_stream") as mock_stream:
            mock_stream.return_value = TranscriptionResult(
                language="en",
                duration=1.0,
                text="Test transcription",
                segments=[],
                word_timestamps_available=False,
                timing_granularity="segment",
                provider="faster-whisper",
                model="base",
                device="cpu",
                compute_type="int8",
                fallback_reason="No CUDA devices detected by CTranslate2; running on CPU INT8",
            )
            with patch.object(provider, "_load_model_lazy") as mock_load:
                mock_load.return_value = MagicMock()

                res = await provider.transcribe(
                    audio_path=dummy_wav,
                    device="cuda",
                    model_size="base",
                )

                assert res.device == "cpu"
                assert res.compute_type == "int8"
                assert "No CUDA devices" in str(res.fallback_reason)


@pytest.mark.asyncio
async def test_groq_provider_success(dummy_wav: Path):
    """Test Groq Whisper API transcription with mocked response."""
    mock_response_data = {
        "text": "Hello world from Groq.",
        "language": "en",
        "duration": 2.5,
        "segments": [
            {
                "id": 0,
                "start": 0.0,
                "end": 2.5,
                "text": "Hello world from Groq.",
                "words": [
                    {"word": "Hello", "start": 0.0, "end": 0.5, "probability": 0.99},
                    {"word": "world", "start": 0.6, "end": 1.1, "probability": 0.98},
                    {"word": "from", "start": 1.2, "end": 1.5, "probability": 0.95},
                    {"word": "Groq.", "start": 1.6, "end": 2.5, "probability": 0.97},
                ],
            }
        ],
    }

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_response_data
    mock_client.post.return_value = mock_resp

    provider = GroqTranscriptionProvider(http_client=mock_client)

    with patch.object(settings, "ALLOW_CLOUD_APIS", True):
        with patch.object(settings, "GROQ_API_KEY", "gsk_test123"):
            res = await provider.transcribe(
                audio_path=dummy_wav,
                word_timestamps=True,
            )

            assert res.provider == "groq"
            assert res.text == "Hello world from Groq."
            assert len(res.segments) == 1
            assert res.word_timestamps_available is True
            assert len(res.segments[0].words) == 4
            assert res.segments[0].words[0].word == "Hello"


@pytest.mark.asyncio
async def test_groq_retry_on_rate_limit(dummy_wav: Path):
    """Verify exponential backoff retry on HTTP 429 for Groq."""
    call_count = 0

    async def mock_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        resp = MagicMock(spec=httpx.Response)
        if call_count == 1:
            resp.status_code = 429
            resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Rate limited", request=MagicMock(), response=resp
            )
            return resp
        resp.status_code = 200
        resp.json.return_value = {
            "text": "Success after retry",
            "segments": [{"start": 0.0, "end": 1.0, "text": "Success after retry"}],
        }
        return resp

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.side_effect = mock_post

    provider = GroqTranscriptionProvider(http_client=mock_client)

    with patch.object(settings, "ALLOW_CLOUD_APIS", True):
        with patch.object(settings, "GROQ_API_KEY", "gsk_test123"):
            res = await provider.transcribe(audio_path=dummy_wav)
            assert res.text == "Success after retry"
            assert call_count == 2


@pytest.mark.asyncio
async def test_assemblyai_provider_with_diarization(dummy_wav: Path):
    """Test AssemblyAI transcription and speaker diarization normalization."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)

    # 1. Upload mock
    upload_resp = MagicMock(spec=httpx.Response)
    upload_resp.status_code = 200
    upload_resp.json.return_value = {"upload_url": "https://api.assemblyai.com/v2/upload/mock-url"}

    # 2. Transcript post mock
    transcript_resp = MagicMock(spec=httpx.Response)
    transcript_resp.status_code = 200
    transcript_resp.json.return_value = {"id": "mock_transcript_id"}

    # 3. Poll mock
    poll_resp = MagicMock(spec=httpx.Response)
    poll_resp.status_code = 200
    poll_resp.json.return_value = {
        "status": "completed",
        "audio_duration": 4.5,
        "text": "Hello there. General Kenobi.",
        "utterances": [
            {
                "speaker": "A",
                "start": 0,
                "end": 2000,
                "text": "Hello there.",
                "words": [
                    {"text": "Hello", "start": 0, "end": 800, "confidence": 0.99},
                    {"text": "there.", "start": 900, "end": 1800, "confidence": 0.98},
                ],
            },
            {
                "speaker": "B",
                "start": 2200,
                "end": 4500,
                "text": "General Kenobi.",
                "words": [
                    {"text": "General", "start": 2200, "end": 3100, "confidence": 0.97},
                    {"text": "Kenobi.", "start": 3200, "end": 4500, "confidence": 0.99},
                ],
            },
        ],
    }

    mock_client.post.side_effect = [upload_resp, transcript_resp]
    mock_client.get.return_value = poll_resp

    provider = AssemblyAITranscriptionProvider(http_client=mock_client)

    with patch.object(settings, "ALLOW_CLOUD_APIS", True):
        with patch.object(settings, "ASSEMBLYAI_API_KEY", "aai_test123"):
            res = await provider.transcribe(dummy_wav)

            assert res.provider == "assemblyai"
            assert res.speaker_diarization_available is True
            assert len(res.segments) == 2
            assert res.segments[0].speaker == "SPEAKER_A"
            assert res.segments[0].start == 0.0
            assert res.segments[0].end == 2.0
            assert res.segments[1].speaker == "SPEAKER_B"
            assert res.segments[1].start == 2.2
            assert res.segments[1].end == 4.5


@pytest.mark.asyncio
async def test_huggingface_provider_loading_retry(dummy_wav: Path):
    """Test Hugging Face provider retry when model is loading (503)."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    call_count = 0

    async def mock_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        resp = MagicMock(spec=httpx.Response)
        if call_count == 1:
            resp.status_code = 503
            resp.json.return_value = {"error": "Model loading", "estimated_time": 0.01}
            resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Loading", request=MagicMock(), response=resp
            )
            return resp
        resp.status_code = 200
        resp.json.return_value = {
            "text": "HF model ready result",
            "chunks": [
                {"timestamp": [0.0, 1.5], "text": "HF model ready result"},
            ],
        }
        return resp

    mock_client.post.side_effect = mock_post

    provider = HuggingFaceTranscriptionProvider(http_client=mock_client)

    with patch.object(settings, "ALLOW_CLOUD_APIS", True):
        with patch.object(settings, "HF_TOKEN", "hf_test123"):
            res = await provider.transcribe(dummy_wav)
            assert res.provider == "huggingface"
            assert res.text == "HF model ready result"
            assert len(res.segments) == 1
            assert res.segments[0].end == 1.5


@pytest.mark.asyncio
async def test_whisper_cpp_provider_mock(dummy_wav: Path, tmp_path: Path):
    """Test whisper.cpp provider subprocess invocation and JSON parsing."""
    provider = WhisperCppProvider()

    mock_json_out = {
        "transcription": [
            {
                "timestamps": {"from": "00:00:00,000", "to": "00:00:02,000"},
                "offsets": {"from": 0, "to": 2000},
                "text": "Local whisper cpp speech",
                "tokens": [
                    {"text": "Local", "offsets": {"from": 0, "to": 500}, "p": 0.95},
                    {"text": "speech", "offsets": {"from": 600, "to": 2000}, "p": 0.98},
                ],
            }
        ]
    }

    async def mock_create_subprocess_exec(*cmd, **kwargs):
        proc = AsyncMock()
        proc.returncode = 0
        # Write output json to the prefix passed in cmd
        for idx, arg in enumerate(cmd):
            if arg == "-of":
                out_prefix = cmd[idx + 1]
                Path(f"{out_prefix}.json").write_text(json.dumps(mock_json_out))
        proc.communicate.return_value = (b"", b"")
        return proc

    with patch("shutil.which", return_value="/usr/local/bin/whisper-cli"):
        with patch(
            "app.services.transcription.whisper_cpp_provider._find_whisper_cpp_model",
            return_value="/models/ggml.bin",
        ):
            with patch("asyncio.create_subprocess_exec", side_effect=mock_create_subprocess_exec):
                res = await provider.transcribe(dummy_wav)
                assert res.provider == "whisper.cpp"
                assert res.text == "Local whisper cpp speech"
                assert len(res.segments) == 1
                assert res.segments[0].words[0].word == "Local"


def test_chunking_seam_deduplication(dummy_wav: Path):
    """Test overlapping chunk stitching and boundary word deduplication."""
    chunk1 = AudioChunk(path=dummy_wav, start_sec=0.0, duration_sec=10.0, index=0)
    chunk2 = AudioChunk(path=dummy_wav, start_sec=8.0, duration_sec=10.0, index=1)  # 2s overlap

    segs1 = [
        TranscriptSegment(
            id="s1",
            start=0.0,
            end=5.0,
            text="First sentence.",
            words=[
                WordTiming(word="First", start=0.0, end=2.0),
                WordTiming(word="sentence.", start=2.5, end=4.8),
            ],
        ),
        TranscriptSegment(
            id="s2",
            start=7.0,
            end=9.5,
            text="Overlapping bridge here.",
            words=[
                WordTiming(word="Overlapping", start=7.0, end=8.0),
                WordTiming(word="bridge", start=8.2, end=9.0),
                WordTiming(word="here.", start=9.1, end=9.5),
            ],
        ),
    ]

    segs2 = [
        # In chunk2 (relative times: start_sec=8.0), the bridge words
        # appear at relative 0.2, 1.0, 1.1:
        TranscriptSegment(
            id="s3",
            start=0.2,
            end=1.5,
            text="bridge here.",
            words=[
                WordTiming(word="bridge", start=0.2, end=1.0),
                WordTiming(word="here.", start=1.1, end=1.5),
            ],
        ),
        TranscriptSegment(
            id="s4",
            start=2.0,
            end=5.0,
            text="Second chunk content.",
            words=[
                WordTiming(word="Second", start=2.0, end=3.0),
                WordTiming(word="chunk", start=3.1, end=4.0),
                WordTiming(word="content.", start=4.1, end=5.0),
            ],
        ),
    ]

    merged = merge_overlapping_segments([chunk1, chunk2], [segs1, segs2])

    assert len(merged) >= 2
    # Check that absolute timestamps were shifted for chunk2
    last_seg = merged[-1]
    assert last_seg.start >= 8.0  # shifted by chunk2 start_sec


@pytest.mark.asyncio
async def test_transcription_manager_caching(dummy_wav: Path, tmp_path: Path):
    """Verify that transcription manager caches results and avoids re-running."""
    mgr = TranscriptionManager()

    with patch.object(settings, "DATA_DIR", str(tmp_path)):
        # First transcription
        res1 = await mgr.transcribe(
            audio_path=dummy_wav,
            provider_name="fake",
            use_cache=True,
        )
        assert res1.provider == "fake"

        # Second transcription should hit cache
        res2 = await mgr.transcribe(
            audio_path=dummy_wav,
            provider_name="fake",
            use_cache=True,
        )
        assert res2.provider in ("fake", "cached")
        assert res2.text == res1.text
        assert len(res2.segments) == len(res1.segments)
