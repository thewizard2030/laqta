"""Tests for stage s01_ingest and stage s02_transcript (Pass 1 / Pass 2).

Strategy:
- Synthetic 16 kHz mono audio: gaussian-noise "speech" bursts separated by
  real 500 ms silences, generated with numpy and written with the stdlib
  ``wave`` module (no soundfile/librosa dependency).
- Mock transcription adapters verify the ADAPTER CONTRACT (prompt, language,
  offset math) without downloading Whisper weights.
- Groq chunking/offsets use ``httpx.MockTransport`` — no network access.
- Stage s01 uses real ffprobe/ffmpeg (skipped when unavailable).
"""

import asyncio
import os
import shutil
import subprocess
import wave
from pathlib import Path

import httpx
import numpy as np
import pytest

from qatta.core.config import QattaSettings
from qatta.core.pipeline import PipelineError, PipelineOrchestrator
from qatta.core.schema import (
    ClipCandidate,
    CPSBreakdown,
    HookRemixVariant,
    QattaManifest,
    VetoGates,
)
from qatta.stages.s01_ingest.ingestor import (
    is_url,
    probe_media,
    run_ingest_stage,
)
from qatta.stages.s02_transcript import fine_pass
from qatta.stages.s02_transcript.fast_pass import (
    ARABISH_INITIAL_PROMPT,
    GroqWhisperTranscriber,
    TranscriptionAdapter,
    TranscriptSegment,
    WordTiming,
    audio_total_ms,
    build_atomic_utterances,
    detect_speech_runs,
    load_pcm_16k,
    run_fast_pass_stage,
    silence_intervals_of,
    write_wav_16bit,
)

SR = 16000


# ---------------------------------------------------------------------------
# Synthetic audio: 4 noise bursts, real 500 ms pauses between them
# ---------------------------------------------------------------------------
# bursts (ms): [0,2000)  [2500,4500)  [5000,6500)  [7000,8500), tail to 10000


def make_synthetic_pcm() -> np.ndarray:
    # Uniform noise (bounded, no clipping tails) so the 16-bit WAV
    # round-trip is bit-exact and the RMS ratios stay clean.
    rng = np.random.default_rng(42)
    pcm = np.zeros(10 * SR, dtype=np.float32)
    spans = [(0, 2000, 0.9), (2500, 4500, 0.7), (5000, 6500, 0.5), (7000, 8500, 0.3)]
    for start_ms, end_ms, amp in spans:
        i0 = start_ms * SR // 1000
        i1 = end_ms * SR // 1000
        pcm[i0:i1] = rng.uniform(-amp, amp, i1 - i0).astype(np.float32)
    return pcm


@pytest.fixture
def pcm_10s() -> np.ndarray:
    return make_synthetic_pcm()


@pytest.fixture
def wav_10s(pcm_10s, tmp_path: Path) -> Path:
    path = tmp_path / "audio_16k.wav"
    write_wav_16bit(pcm_10s, SR, path)
    return path


def make_settings(tmp_path: Path, **overrides) -> QattaSettings:
    # URL ingestion is fail-closed in production (it ships disabled). The
    # tests that exercise the enabled path opt in explicitly.
    options = {"enable_url_ingestion": True}
    options.update(overrides)
    return QattaSettings(data_dir=tmp_path / "data", _env_file=None, **options)


def make_candidate(
    clip_id: str,
    start_ms: int,
    end_ms: int,
    start_u: str = "U_0001",
    end_u: str = "U_0002",
) -> ClipCandidate:
    return ClipCandidate(
        clip_id=clip_id,
        start_u_id=start_u,
        end_u_id=end_u,
        start_ms=start_ms,
        end_ms=end_ms,
        duration_sec=(end_ms - start_ms) / 1000.0,
        veto_gates=VetoGates(
            dangling_context=False,
            clean_audio_boundaries=True,
            crosstalk_ratio=0.05,
            passed_all=True,
        ),
        cps=CPSBreakdown(
            total_score=70.0,
            archetype="STORY",
            standalone_clarity=8.0,
            hook_strength=8.0,
            story_payoff=7.0,
            value_originality=6.0,
            audio_dynamics=7.0,
            boundary_precision=8.0,
        ),
        hook_remix=HookRemixVariant(enabled=False),
    )


# ---------------------------------------------------------------------------
# Mock adapters (verify the adapter contract, no real model)
# ---------------------------------------------------------------------------


class MockSegmentAdapter(TranscriptionAdapter):
    def __init__(self, segments: list[TranscriptSegment]):
        self.segments = segments
        self.calls: list[dict] = []

    def transcribe(self, pcm, sr=16000, initial_prompt=None, language=None):
        self.calls.append(
            {
                "samples": len(pcm),
                "sr": sr,
                "initial_prompt": initial_prompt,
                "language": language,
            }
        )
        return list(self.segments)


class MockWordAdapter(TranscriptionAdapter):
    """Returns slice-RELATIVE words; the pass must convert to absolute."""

    def __init__(self, calls: list[list[WordTiming]]):
        self.calls = calls
        self.received: list[dict] = []
        self._i = 0

    def transcribe_words(self, pcm, sr=16000, language=None, beam_size=2):
        self.received.append({"samples": len(pcm), "language": language, "beam": beam_size})
        words = self.calls[min(self._i, len(self.calls) - 1)]
        self._i += 1
        return list(words)


# ---------------------------------------------------------------------------
# Pause detection + utterance building
# ---------------------------------------------------------------------------


def test_detect_speech_runs_find_real_burst_boundaries(pcm_10s) -> None:
    runs = detect_speech_runs(pcm_10s, SR, silence_ms=350)
    expected = [(0, 2000), (2500, 4500), (5000, 6500), (7000, 8500)]
    assert len(runs) == 4
    for (es, ee), (rs, re_) in zip(expected, runs, strict=True):
        assert abs(rs - es) <= 60, (rs, es)
        assert abs(re_ - ee) <= 60, (re_, ee)


def test_silence_intervals_are_the_complement(pcm_10s) -> None:
    runs = detect_speech_runs(pcm_10s, SR, silence_ms=350)
    silences = silence_intervals_of(runs, audio_total_ms(pcm_10s, SR))
    # Every real ≥350ms pause between bursts overlaps one silence interval
    # by at least the threshold (run edges are frame-quantized ±~50 ms).
    for gap in [(2000, 2500), (4500, 5000), (6500, 7000), (8500, 10000)]:
        overlap = max(
            (min(s1, gap[1]) - max(s0, gap[0]) for s0, s1 in silences),
            default=0,
        )
        assert overlap >= 350, (gap, silences, overlap)


def test_build_atomic_utterances_split_and_pause(pcm_10s) -> None:
    segments = [
        TranscriptSegment(0, 2000, "أول درس"),
        TranscriptSegment(2500, 4500, "history class"),
        TranscriptSegment(5000, 6500, "AI tools"),
        TranscriptSegment(7000, 8500, "نهاية الحلقة"),
    ]
    runs = detect_speech_runs(pcm_10s, SR, silence_ms=350)
    utts = build_atomic_utterances(segments, runs, 10000, pcm_10s, SR, pause_ms=350)

    assert [u.u_id for u in utts] == ["U_0001", "U_0002", "U_0003", "U_0004"]
    assert [u.start_ms for u in utts] == [0, 2500, 5000, 7000]
    assert all(abs(u.end_ms - e) <= 5 for u, e in zip(utts, [2000, 4500, 6500, 8500], strict=True))
    # pause_after_ms equals the REAL acoustic gap (500 ms).
    assert [u.pause_after_ms for u in utts] == [500, 500, 500, 0]
    # Loudness declines across bursts; the loudest is normalized to ~1.0.
    assert utts[0].audio_rms_norm == pytest.approx(1.0, abs=0.05)
    assert utts[3].audio_rms_norm == pytest.approx(0.3 / 0.9, abs=0.08)
    assert all(u.words == [] for u in utts)
    assert "history" in utts[1].text


def test_segments_without_acoustic_pause_are_merged(pcm_10s) -> None:
    segments = [
        TranscriptSegment(0, 900, "هذا"),
        TranscriptSegment(1100, 2000, "الدرس الأول"),
    ]
    runs = detect_speech_runs(pcm_10s, SR, silence_ms=350)
    utts = build_atomic_utterances(segments, runs, 10000, pcm_10s, SR, pause_ms=350)
    assert len(utts) == 1
    assert utts[0].text == "هذا الدرس الأول"


def test_no_acoustic_runs_falls_back_to_long_asr_gaps(pcm_10s) -> None:
    """Degraded mode: no speech runs -> split only on long ASR gaps."""
    segments = [
        TranscriptSegment(0, 2000, "جزء أول"),
        TranscriptSegment(3000, 4500, "جزء ثانٍ"),
    ]
    utts = build_atomic_utterances(segments, [], 10000, pcm_10s, SR, pause_ms=350)
    assert len(utts) == 2
    assert utts[1].start_ms == 3000


def test_built_utterances_validate_against_strict_schema(wav_10s, tmp_path: Path) -> None:
    pcm, sr = load_pcm_16k(wav_10s)
    runs = detect_speech_runs(pcm, SR, silence_ms=350)
    utts = build_atomic_utterances(
        [
            TranscriptSegment(0, 2000, "أول"),
            TranscriptSegment(2500, 4500, "history AI"),
        ],
        runs,
        audio_total_ms(pcm, sr),
        pcm,
        sr,
    )
    manifest = QattaManifest(
        project_id="proj_x",
        source_path=str(tmp_path / "src.wav"),
        duration_sec=10.0,
        atomic_utterances=utts,
    )
    # extra="forbid" + validators must accept the stage's output.
    assert QattaManifest.model_validate(manifest.model_dump())


# ---------------------------------------------------------------------------
# load_pcm_16k
# ---------------------------------------------------------------------------


def test_load_pcm_16k_roundtrip(wav_10s, pcm_10s) -> None:
    pcm, sr = load_pcm_16k(wav_10s)
    assert sr == SR
    np.testing.assert_allclose(pcm, pcm_10s, atol=1 / 32768)


def test_load_pcm_16k_rejects_wrong_layout(tmp_path: Path) -> None:
    path = tmp_path / "wrong.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(44100)
        handle.writeframes(b"\x00\x01" * 44100)
    with pytest.raises(PipelineError) as exc_info:
        load_pcm_16k(path)
    assert "16 kHz" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Stage s01_ingest
# ---------------------------------------------------------------------------


def test_ingest_stage_probe_and_extract(tmp_path: Path) -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("ffmpeg/ffprobe unavailable")
    media = tmp_path / "sample.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=2:size=160x120:rate=5",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2:sample_rate=16000",
            "-c:v",
            "mpeg4",
            "-c:a",
            "aac",
            "-t",
            "2",
            str(media),
        ],
        capture_output=True,
        check=True,
    )
    settings = make_settings(tmp_path)
    manifest = QattaManifest(project_id="proj_ingest", source_path=str(media), duration_sec=2.0)
    result = run_ingest_stage(manifest, settings, work_dir=tmp_path)

    assert result.audio_16k_path is not None
    audio = Path(result.audio_16k_path)
    assert audio.is_file() and audio.stat().st_size > 0
    assert result.video_width == 160
    assert result.video_height == 120
    assert result.fps == pytest.approx(5.0, abs=0.01)
    assert result.duration_sec == pytest.approx(2.0, abs=0.2)
    # The extracted WAV loads with the strict s02 loader.
    pcm, sr = load_pcm_16k(audio)
    assert sr == 16000 and len(pcm) >= int(1.9 * SR)


def test_ingest_url_requires_ingestion_enabled(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path,
        enable_url_ingestion=False,  # explicit FR-12 opt-out
    )
    assert is_url("https://example.com/lecture.mp4")
    assert not is_url("/home/user/video.mp4")
    manifest = QattaManifest(
        project_id="proj_url",
        source_path="https://example.com/lecture.mp4",
        duration_sec=1.0,
    )
    with pytest.raises(PipelineError) as exc_info:
        run_ingest_stage(manifest, settings, work_dir=tmp_path)
    assert "QATTA_ENABLE_URL_INGESTION" in str(exc_info.value)
    # Nothing was downloaded or created.
    assert not (tmp_path / "source_media").exists()


def test_probe_media_reports_resolution_fps(tmp_path: Path) -> None:
    if shutil.which("ffprobe") is None:
        pytest.skip("ffprobe unavailable")
    media = tmp_path / "probe.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=1:size=64x64:rate=5",
            "-c:v",
            "mpeg4",
            "-t",
            "1",
            str(media),
        ],
        capture_output=True,
        check=True,
    )
    probed = probe_media(media, make_settings(tmp_path))
    assert probed.duration_sec == pytest.approx(1.0, abs=0.2)
    assert probed.width == 64 and probed.height == 64
    assert probed.fps == pytest.approx(5.0, abs=0.01)


# ---------------------------------------------------------------------------
# Stage s02 — Pass 1 (fast pass) with mock adapters
# ---------------------------------------------------------------------------


def test_fast_pass_builds_utterances_via_adapter(wav_10s, tmp_path: Path) -> None:
    adapter = MockSegmentAdapter(
        [
            TranscriptSegment(0, 2000, "أول"),
            TranscriptSegment(2500, 4500, "history AI"),
            TranscriptSegment(5000, 6500, "tools"),
            TranscriptSegment(7000, 8500, "النهاية"),
        ]
    )
    settings = make_settings(tmp_path)
    manifest = QattaManifest(
        project_id="proj_pass1",
        source_path=str(wav_10s),
        duration_sec=10.0,
        audio_16k_path=str(wav_10s),
    )
    result = run_fast_pass_stage(manifest, settings, adapter=adapter)
    assert len(result.atomic_utterances) == 4
    # The adapter contract: Arablish prompt + mapped language.
    assert len(adapter.calls) == 1
    call = adapter.calls[0]
    assert call["initial_prompt"] == ARABISH_INITIAL_PROMPT
    assert call["language"] == "ar"  # from language_profile "ar-EG-mixed"
    assert call["sr"] == 16000


def test_fast_pass_requires_ingest_first(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    manifest = QattaManifest(
        project_id="proj_ning",
        source_path="/nowhere/x.mp4",
        duration_sec=1.0,
    )
    with pytest.raises(PipelineError) as exc_info:
        run_fast_pass_stage(manifest, settings)
    assert "s01_ingest" in str(exc_info.value)


def test_fast_pass_refuses_gated_cloud_backend(wav_10s, tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path,
        transcription_backend="groq_api",
        groq_api_key="unused",
        allow_cloud_apis=False,
    )
    manifest = QattaManifest(
        project_id="proj_gate",
        source_path=str(wav_10s),
        duration_sec=10.0,
        audio_16k_path=str(wav_10s),
    )
    with pytest.raises(PipelineError) as exc_info:
        run_fast_pass_stage(manifest, settings)
    assert "ALLOW_CLOUD_APIS" in str(exc_info.value)


def test_fast_pass_youtube_backend_permitted_when_enabled(wav_10s, tmp_path: Path) -> None:
    """youtube_subs_first is now real; without a caption file it fails
    honestly instead of transcoding locally (no silent fallback)."""
    settings = make_settings(
        tmp_path,
        transcription_backend="youtube_subs_first",
    )
    manifest = QattaManifest(
        project_id="proj_yt",
        source_path=str(wav_10s),
        duration_sec=10.0,
        audio_16k_path=str(wav_10s),
    )
    with pytest.raises(PipelineError) as exc_info:
        run_fast_pass_stage(manifest, settings)
    assert "subtitle_path" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Groq adapter: chunking, headers, offsets — via httpx.MockTransport
# ---------------------------------------------------------------------------


def test_groq_adapter_chunks_offsets_and_contract(tmp_path: Path) -> None:
    # 5 s of speech-like noise → chunk_seconds=2 → chunks at 0/2000/4000 ms.
    rng = np.random.default_rng(7)
    pcm = (rng.standard_normal(5 * SR) * 0.5).astype(np.float32)

    posted: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request.read()  # materialize the multipart body for assertions
        posted.append(request)
        index = len(posted) - 1
        return httpx.Response(
            200,
            json={
                "segments": [
                    {
                        "start": 0.05,
                        "end": 0.95,
                        "text": f"chunk {index} نص",
                    }
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=10.0)
    transcriber = GroqWhisperTranscriber(
        api_key="test-key",
        base_url="http://groq.test/v1",
        chunk_seconds=2,
        max_concurrency=2,
        timeout_seconds=10.0,
        http_client=client,
    )
    segments = asyncio.run(
        transcriber.transcribe_async(pcm, SR, initial_prompt="محاضرة مصري", language="ar")
    )

    assert len(posted) == 3
    for request in posted:
        assert request.url.path.endswith("/audio/transcriptions")
        assert request.headers["Authorization"] == "Bearer test-key"
        body = request.content
        assert b"whisper-large-v3-turbo" in body
        assert b'name="language"' in body and b"\r\nar\r\n" in body
        assert b'name="prompt"' in body
        assert "محاضرة مصري".encode() in body

    # Offset-corrected absolute milliseconds.
    assert [(s.start_ms, s.end_ms) for s in segments] == [(50, 950), (2050, 2950), (4050, 4950)]
    assert segments[1].text == "chunk 1 نص"
    await_close = asyncio.run(client.aclose())
    del await_close  # test-owned client closed (pytest-httpx safe)


# ---------------------------------------------------------------------------
# Stage s02 — Pass 2 (fine pass): snapping + token population
# ---------------------------------------------------------------------------


def make_manifest_with_candidates(wav_10s: Path, utts) -> QattaManifest:
    return QattaManifest(
        project_id="proj_pass2",
        source_path=str(wav_10s),
        duration_sec=10.0,
        audio_16k_path=str(wav_10s),
        atomic_utterances=utts,
        candidates=[
            make_candidate("c1", 0, 2000),
            make_candidate("c2", 2500, 4500, "U_0002", "U_0003"),
            make_candidate("c3", 5000, 6500, "U_0003", "U_0004"),
        ],
    )


def test_fine_pass_snaps_and_populates_words(wav_10s, pcm_10s, tmp_path):
    runs = detect_speech_runs(pcm_10s, SR, silence_ms=350)
    utts = build_atomic_utterances(
        [
            TranscriptSegment(0, 2000, "أول"),
            TranscriptSegment(2500, 4500, "history AI"),
            TranscriptSegment(5000, 6500, "tools"),
            TranscriptSegment(7000, 8500, "النهاية"),
        ],
        runs,
        10000,
        pcm_10s,
        SR,
    )
    manifest = make_manifest_with_candidates(wav_10s, utts)

    # Slice-relative word timings per winner, in call order (c1 then c2).
    adapter = MockWordAdapter(
        calls=[
            [
                WordTiming("مثال", 300, 600, 0.95),
                WordTiming("history", 700, 1100, 0.9),
            ],
            [
                WordTiming("تجربة", 400, 700, 0.92),  # abs 2400–2700
                WordTiming("سيارة", 900, 1300, 0.88),  # abs 2900–3300
            ],
        ]
    )
    settings = make_settings(tmp_path, fine_padding_ms=500)

    result = fine_pass.align_winner_words(manifest, ["c1", "c2"], settings, adapter=adapter)

    # c1: slice [0, 2500] → words absolute at 300/1100.
    c1 = next(c for c in result.candidates if c.clip_id == "c1")
    assert c1.start_ms == 180  # 300 - 120 snap
    assert c1.end_ms == 1220  # 1100 + 120 snap
    assert c1.duration_sec == pytest.approx((1220 - 180) / 1000)
    assert any("snapped to acoustic boundaries" in e for e in c1.evidence_log)

    # c2: slice [2000, 5000]; offset conversion is REQUIRED for these asserts.
    c2 = next(c for c in result.candidates if c.clip_id == "c2")
    assert c2.start_ms == 2280  # (2000 + 400) - 120
    assert c2.end_ms == 3420  # (2000 + 1300) + 120
    assert c2.duration_sec == pytest.approx((3420 - 2280) / 1000)

    # c3 was NOT in winners: unchanged boundaries.
    c3 = next(c for c in result.candidates if c.clip_id == "c3")
    assert c3.start_ms == 5000 and c3.end_ms == 6500

    # WordToken population: tokens attach by midpoint containment.
    u1 = next(u for u in result.atomic_utterances if u.u_id == "U_0001")
    assert [(w.word, w.start_ms, w.end_ms, w.is_latin) for w in u1.words] == [
        ("مثال", 300, 600, False),
        ("history", 700, 1100, True),
    ]
    u2 = next(u for u in result.atomic_utterances if u.u_id == "U_0002")
    assert [(w.word, w.start_ms) for w in u2.words] == [
        ("تجربة", 2400),
        ("سيارة", 2900),
    ]
    u3 = next(u for u in result.atomic_utterances if u.u_id == "U_0003")
    assert u3.words == []
    # Confidence in [0, 1] everywhere.
    assert all(0 <= w.confidence <= 1 for u in result.atomic_utterances for w in u.words)


def test_fine_pass_parameters_reach_adapter(wav_10s, pcm_10s, tmp_path) -> None:
    runs = detect_speech_runs(pcm_10s, SR, silence_ms=350)
    utts = build_atomic_utterances([TranscriptSegment(0, 2000, "أول")], runs, 10000, pcm_10s, SR)
    manifest = make_manifest_with_candidates(wav_10s, utts)
    adapter = MockWordAdapter(calls=[[]])  # no words → fallback note
    settings = make_settings(tmp_path, fine_padding_ms=500)

    result = fine_pass.align_winner_words(manifest, ["c1"], settings, adapter=adapter)
    # beam and language reached the adapter.
    assert adapter.received[0]["beam"] == settings.fine_beam_size
    assert adapter.received[0]["language"] == "ar"

    c1 = next(c for c in result.candidates if c.clip_id == "c1")
    assert (c1.start_ms, c1.end_ms) == (0, 2000)  # unchanged
    assert any("no words detected inside the clip slice" in e for e in c1.evidence_log)


def test_fine_pass_survives_adapter_failure(wav_10s, pcm_10s, tmp_path) -> None:
    runs = detect_speech_runs(pcm_10s, SR, silence_ms=350)
    utts = build_atomic_utterances([TranscriptSegment(0, 2000, "أول")], runs, 10000, pcm_10s, SR)
    manifest = make_manifest_with_candidates(wav_10s, utts)

    class FailingAdapter(TranscriptionAdapter):
        def transcribe_words(self, pcm, sr=16000, language=None, beam_size=2):
            raise RuntimeError("model exploded")

    settings = make_settings(tmp_path)
    result = fine_pass.align_winner_words(manifest, ["c1"], settings, adapter=FailingAdapter())
    c1 = next(c for c in result.candidates if c.clip_id == "c1")
    assert (c1.start_ms, c1.end_ms) == (0, 2000)  # no fabricated alignment
    assert any("word alignment failed" in e for e in c1.evidence_log)
    # Utterances untouched (no words attached).
    assert all(u.words == [] for u in result.atomic_utterances)


def test_fine_pass_rejects_unknown_clip_ids(wav_10s, tmp_path) -> None:
    settings = make_settings(tmp_path)
    manifest = make_manifest_with_candidates(wav_10s, [])
    with pytest.raises(PipelineError) as exc_info:
        fine_pass.align_winner_words(
            manifest,
            ["missing_clip"],
            settings,
            adapter=MockWordAdapter(calls=[[]]),
        )
    assert "missing_clip" in str(exc_info.value)


def test_fine_pass_empty_winners_is_noop(wav_10s, tmp_path) -> None:
    settings = make_settings(tmp_path)
    manifest = make_manifest_with_candidates(wav_10s, [])
    result = fine_pass.run_fine_alignment_stage(manifest, [], settings)
    assert result is manifest


# ---------------------------------------------------------------------------
# Orchestrator registration + stage caching (no real ASR)
# ---------------------------------------------------------------------------


def test_orchestrator_registers_stages_and_caches(wav_10s, tmp_path: Path) -> None:
    from qatta.stages.s01_ingest import ingestor
    from qatta.stages.s02_transcript import fast_pass as fp_fast_pass

    settings = make_settings(tmp_path)
    adapter = MockSegmentAdapter(
        [
            TranscriptSegment(0, 2000, "أول"),
            TranscriptSegment(2500, 4500, "history AI"),
        ]
    )
    orchestrator = PipelineOrchestrator(
        project_id="proj_e2e",
        source_path=wav_10s,
        settings=settings,
    )
    ingestor.register(orchestrator)
    fp_fast_pass.register(orchestrator, adapter=adapter)

    report = orchestrator.run_stage("s01_ingest")
    assert report["executed"] is True
    audio_path = Path(orchestrator.manifest.audio_16k_path)
    assert audio_path.is_file()
    assert audio_path.name == "audio_16k.wav"
    assert orchestrator.work_dir in audio_path.parents

    report = orchestrator.run_stage("s02_transcript")
    assert report["executed"] is True
    assert len(orchestrator.manifest.atomic_utterances) == 2

    # Stage caching: re-runs skip (artifact-based).
    assert orchestrator.run_stage("s01_ingest")["executed"] is False
    assert orchestrator.run_stage("s02_transcript")["executed"] is False
    assert orchestrator.manifest.completed_stages == ["s01_ingest", "s02_transcript"]


def test_orchestrator_gates_cloud_transcription_stage(wav_10s, tmp_path: Path) -> None:
    from qatta.stages.s01_ingest import ingestor
    from qatta.stages.s02_transcript import fast_pass as fp_fast_pass

    settings = make_settings(
        tmp_path,
        transcription_backend="groq_api",
        groq_api_key=None,
        allow_cloud_apis=True,
    )
    orchestrator = PipelineOrchestrator(
        project_id="proj_cloud",
        source_path=wav_10s,
        settings=settings,
    )
    ingestor.register(orchestrator)
    fp_fast_pass.register(orchestrator)

    assert orchestrator.run_stage("s01_ingest")["executed"] is True
    with pytest.raises(PipelineError) as exc_info:
        orchestrator.run_stage("s02_transcript")
    assert "opt-in" in str(exc_info.value)
    # Nothing pretended to run.
    assert "s02_transcript" not in orchestrator.manifest.completed_stages


# ---------------------------------------------------------------------------
# Opt-in REAL-WEIGHTS smoke test (never run in CI without explicit env)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not os.environ.get("QATTA_TEST_REAL_WEIGHTS"),
    reason="opt-in test requiring faster-whisper + model weights; CI must not download weights",
)
def test_local_turbo_smoke_on_real_weights(wav_10s, tmp_path) -> None:
    """Run the real CPU adapter on 10 s of tone-noise audio.

    Asserts only that the adapter runs end-to-end and returns a list of
    segments — the guarantee is the COMPATIBILITY of the rtc plumbing, not
    transcript quality (tone/noise transcribes to garbage on purpose).
    """
    from qatta.stages.s02_transcript.fast_pass import (
        LocalTurboBatchedTranscriber,
    )

    adapter = LocalTurboBatchedTranscriber(model_name="tiny", device="cpu", compute_type="int8")
    try:
        plan = adapter.resolve_compute_plan()
        assert plan == {"device": "cpu", "compute_type": "int8", "batch_size": 4}
        pcm, sr = load_pcm_16k(wav_10s)
        segments = adapter.transcribe(pcm, sr, initial_prompt=ARABISH_INITIAL_PROMPT, language="ar")
        assert isinstance(segments, list)
    finally:
        adapter.close()
