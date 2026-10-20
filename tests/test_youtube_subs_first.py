"""Tests for the YouTube captions-first flow (transcript_source ==
``youtube_subs_first``).

Coverage:
- VTT parsing + auto-caption rolling dedup (pure stdlib, deterministic).
- Pass 1 building AtomicUtterances from platform cue timings only (no
  Whisper, no full audio).
- s01_ingest subs-first branch with a FAKE yt_dlp module (no network).
- s05b section fetching with a FAKE yt_dlp module and a stubbed audio
  extractor (no ffmpeg needed, no network).
- Pass 2 word alignment from a downloaded section with offset math.
- Orchestrator-stage wall-time MEASUREMENT (presence + positivity only;
  absolute numbers are machine-dependent by design).
"""

import json
import sys
import types
import wave
from pathlib import Path

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
from qatta.stages.s01_ingest.ingestor import run_ingest_stage
from qatta.stages.s02_transcript import fast_pass, fine_pass
from qatta.stages.s02_transcript.fast_pass import (
    WordTiming,
    run_fast_pass_stage,
    write_wav_16bit,
)
from qatta.stages.s02_transcript.youtube_subs import (
    dedup_rolling_cues,
    parse_vtt_cues,
    parse_vtt_ms,
    segments_from_youtube_subs,
)
from qatta.stages.s05b_section_fetch import section_fetch

SR = 16000

VTT_ROLLING = """WEBVTT
Kind: captions
Language: ar

00:00:01.000 --> 00:00:03.000 align:start position:0%
السلام عليكم
وفي هذا الفيديو

00:00:03.000 --> 00:00:06.000
وفي هذا الفيديو
نتحدث عن الـ AI والـ SaaS

00:00:06.000 --> 00:00:08.500
نتحدث عن الـ AI والـ SaaS
وكيف تبني منتجك

00:00:12.000 --> 00:00:15.000
ولا تنسى الـ ROI
"""


def make_settings(tmp_path: Path, **overrides) -> QattaSettings:
    return QattaSettings(data_dir=tmp_path / "data", _env_file=None, **overrides)


def make_candidate(
    clip_id: str,
    start_ms: int,
    end_ms: int,
    section_media: Path | None = None,
    section_audio: Path | None = None,
    section_start: int | None = None,
) -> ClipCandidate:
    payload = dict(
        clip_id=clip_id,
        start_u_id="U_0001",
        end_u_id="U_0002",
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
    if section_media is not None:
        payload["section_media_path"] = str(section_media)
    if section_audio is not None:
        payload["section_audio_16k_path"] = str(section_audio)
    if section_start is not None:
        payload["section_start_ms"] = section_start
    return ClipCandidate.model_validate(payload)


def write_wav(pcm: np.ndarray, path: Path) -> Path:
    write_wav_16bit(pcm, SR, path)
    return path


def wav_ms(path: Path) -> int:
    with wave.open(str(path), "rb") as handle:
        return int(handle.getnframes() * 1000 / handle.getframerate())


# ---------------------------------------------------------------------------
# VTT parsing + rolling dedup
# ---------------------------------------------------------------------------


def test_parse_vtt_cues_basic_and_short_form() -> None:
    vtt = (
        "WEBVTT\n\n"
        "01:02:03.004 --> 01:02:05,006\nمرحبا\n\n"
        "05:00.000 --> 07:00.000 align:start\nسطر\n"
    )
    cues = parse_vtt_cues(vtt)
    assert [(c.start_ms, c.end_ms) for c in cues] == [
        (3723004, 3725006),
        (300000, 420000),
    ]


def test_parse_vtt_ms_rejects_garbage() -> None:
    with pytest.raises(PipelineError):
        parse_vtt_ms("01:02:03")


def test_rolling_dedup_keeps_novel_suffix_only() -> None:
    cues = parse_vtt_cues(VTT_ROLLING)
    seen = [
        ("السلام عليكم", "وفي هذا الفيديو"),
        ("نتحدث عن الـ AI والـ SaaS",),
        ("وكيف تبني منتجك",),
        ("ولا تنسى الـ ROI",),
    ]
    deduped = dedup_rolling_cues(cues)
    assert [c.lines for c in deduped] == [tuple(s) for s in seen]
    # Timestamps follow the cue that FIRST carries the novel lines.
    assert deduped[0].start_ms == 1000
    assert deduped[1].start_ms == 3000
    # Manual (non-rolling) 4th cue is untouched: no repetition.
    assert deduped[-1].start_ms == 12000


def test_segments_from_youtube_subs() -> None:
    segments = segments_from_youtube_subs(VTT_ROLLING, total_ms=15000)
    texts = [s.text for s in segments]
    assert texts == [
        "السلام عليكم وفي هذا الفيديو",
        "نتحدث عن الـ AI والـ SaaS",
        "وكيف تبني منتجك",
        "ولا تنسى الـ ROI",
    ]
    assert all(s.start_ms <= s.end_ms for s in segments)


# ---------------------------------------------------------------------------
# Pass 1 from captions only
# ---------------------------------------------------------------------------


def subtitle_manifest(tmp_path: Path, duration: float = 20.0) -> QattaManifest:
    subtitle = tmp_path / "captions.ar.vtt"
    subtitle.write_text(VTT_ROLLING, encoding="utf-8")
    return QattaManifest(
        project_id="proj_captions",
        source_path="youtube:dQw4w9WgXcQ",
        source_url="https://youtube.com/watch?v=dQw4w9WgXcQ",
        duration_sec=duration,
        subtitle_path=str(subtitle),
    )


def test_fast_pass_captions_first_builds_utterances(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path, transcription_backend="youtube_subs_first")
    manifest = subtitle_manifest(tmp_path)
    result = run_fast_pass_stage(manifest, settings)
    assert result.transcript_source == "youtube_subs_first"
    texts = [u.text for u in result.atomic_utterances]
    assert texts[0].startswith("السلام عليكم")
    assert "SaaS" in " ".join(texts)  # Arablish kept in Latin script
    # pause_after_ms derives from real cue gaps.
    assert all(u.pause_after_ms >= 0 for u in result.atomic_utterances)
    # No local audio was measured — documented limitation, not fabricated.
    assert all(u.audio_rms_norm == 0.0 for u in result.atomic_utterances)


def test_fast_pass_captions_requires_subtitle_file(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, transcription_backend="youtube_subs_first")
    manifest = QattaManifest(
        project_id="proj_nosubs",
        source_path="youtube:abc",
        duration_sec=5.0,
    )
    with pytest.raises(PipelineError) as exc_info:
        run_fast_pass_stage(manifest, settings)
    assert "subtitle_path" in str(exc_info.value)


def test_fast_pass_refuses_disabled_url_ingestion(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path,
        transcription_backend="youtube_subs_first",
        enable_url_ingestion=False,
    )
    manifest = subtitle_manifest(tmp_path)
    with pytest.raises(PipelineError) as exc_info:
        run_fast_pass_stage(manifest, settings)
    assert "QATTA_ENABLE_URL_INGESTION" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Fake yt_dlp module injection (no network, no real dependency behavior)
# ---------------------------------------------------------------------------


class FakeYoutubeDL:
    """Duck-typed stand-in for yt_dlp.YoutubeDL recording every option."""

    instances: list["FakeYoutubeDL"] = []

    def __init__(self, options: dict):
        self.options = options
        self.calls: dict | None = dict(options)
        FakeYoutubeDL.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def install_fake_yt_dlp(
    monkeypatch: pytest.MonkeyPatch,
    info: dict,
    files_written: dict[str, bytes] | None = None,
) -> list[FakeYoutubeDL]:
    files_written = files_written or {}

    class FakeModule(types.ModuleType):
        pass

    fake = FakeModule("yt_dlp")

    class _Ydl(FakeYoutubeDL):
        def extract_info(self, url, download=True):
            # Pretend files were written into the configured outtmpl dirs.
            self.info = info
            outtmpl = self.options.get("outtmpl", "")
            if "%(ext)s" in outtmpl:
                path = outtmpl.replace("%(id)s", str(info.get("id", "vid")))
                for ext, payload in files_written.items():
                    Path(path.replace("%(ext)s", ext.replace("*", "ar"))).write_bytes(payload)
            return info

    fake.YoutubeDL = _Ydl
    monkeypatch.setitem(sys.modules, "yt_dlp", fake)
    return FakeYoutubeDL.instances


# ---------------------------------------------------------------------------
# s01_ingest captions-first branch
# ---------------------------------------------------------------------------


def test_ingest_captions_first_fetches_subs_not_media(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = make_settings(tmp_path, transcription_backend="youtube_subs_first")
    manifest = QattaManifest(
        project_id="proj_fetch",
        source_path="https://youtube.com/watch?v=dQw4w9WgXcQ",
        duration_sec=1.0,
    )
    vtt_body = ("WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nمرحبا\n").encode()
    install_fake_yt_dlp(
        monkeypatch,
        info={
            "id": "dQw4w9WgXcQ",
            "duration": 7200.0,
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
        },
        files_written={"vtt": vtt_body},
    )
    original_url = manifest.source_path
    result = run_ingest_stage(manifest, settings, work_dir=tmp_path)

    ydl = FakeYoutubeDL.instances[-1]
    assert ydl.options["skip_download"] is True
    assert ydl.options["writeautomaticsub"] is True
    assert result.audio_16k_path is None  # NO media/audio pipeline ran
    assert result.duration_sec == pytest.approx(7200.0)
    assert result.video_width == 1920 and result.video_height == 1080
    assert result.fps == pytest.approx(30.0)
    assert result.subtitle_path is not None
    assert Path(result.subtitle_path).is_file()
    assert result.source_url == original_url
    assert result.source_path == "youtube:dQw4w9WgXcQ"


def test_ingest_captions_no_track_is_honest_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = make_settings(tmp_path, transcription_backend="youtube_subs_first")
    manifest = QattaManifest(
        project_id="proj_notrack",
        source_path="https://youtube.com/watch?v=x",
        duration_sec=1.0,
    )
    install_fake_yt_dlp(
        monkeypatch,
        info={"id": "x", "duration": 60.0},
        files_written={},  # no VTT written
    )
    with pytest.raises(PipelineError) as exc_info:
        run_ingest_stage(manifest, settings, work_dir=tmp_path)
    assert "No caption track" in str(exc_info.value)
    assert "ar" in str(exc_info.value)


# ---------------------------------------------------------------------------
# s05b section fetch (fake yt-dlp + stubbed audio extraction)
# ---------------------------------------------------------------------------


def test_section_fetch_downloads_only_winners(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = make_settings(tmp_path, fine_padding_ms=2000)
    manifest = QattaManifest(
        project_id="proj_sections",
        source_path="youtube:vid",
        source_url="https://youtube.com/watch?v=vid",
        duration_sec=7200.0,
        transcript_source="youtube_subs_first",
        subtitle_path=str(tmp_path / "c.vtt"),
        candidates=[
            make_candidate("C_0001", 30_000, 60_000),
            # Vetoed candidate: must NOT be fetched.
            make_candidate("C_0002", 10_000, 20_000).model_validate(
                {
                    **make_candidate("C_0002", 10_000, 20_000).model_dump(),
                    "veto_gates": {
                        "dangling_context": True,
                        "clean_audio_boundaries": False,
                        "crosstalk_ratio": 0.9,
                        "passed_all": False,
                        "rejection_reason": "test",
                    },
                }
            ),
        ],
    )
    install_fake_yt_dlp(
        monkeypatch,
        info={
            "id": "vid",
            "requested_downloads": [{"filepath": str(tmp_path / "sections" / "C_0001.mp4")}],
        },
        files_written={"mp4": b"section video bytes"},
    )
    requested: list[dict] = []
    for inst in FakeYoutubeDL.instances:
        requested.append(inst.options)
    # Stub audio extraction (no ffmpeg dependency in unit tests).
    monkeypatch.setattr(
        section_fetch,
        "extract_audio_16k",
        lambda src, dst, _s: _copy_dummy(src, dst),
    )

    def _copy_dummy(src, dst):
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"audio stub")
        Path(src).write_bytes(b"video stub")
        return dst

    result = section_fetch.run_section_fetch_stage(manifest, settings, work_dir=tmp_path)

    ydl = FakeYoutubeDL.instances[-1]
    ranges = ydl.options["download_ranges"](None, None)
    assert ranges == [{"start": 28.0, "end": 62.0}]  # padding ±2 s
    assert ydl.options["force_keyframes_at_cuts"] is True
    assert ydl.options["noplaylist"] is True

    winner = result.candidates[0]
    assert winner.section_audio_16k_path is not None
    assert winner.section_start_ms == 28_000
    assert any("s05b" in entry for entry in winner.evidence_log)
    # Vetoed clip untouched.
    assert result.candidates[1].section_media_path is None


def test_section_fetch_refuses_disabled_download(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, enable_url_ingestion=False)
    manifest = QattaManifest(
        project_id="proj_gate",
        source_path="youtube:vid",
        source_url="https://youtube.com/watch?v=vid",
        duration_sec=60.0,
        transcript_source="youtube_subs_first",
        subtitle_path=str(tmp_path / "c.vtt"),
        candidates=[make_candidate("C_0001", 1_000, 10_000)],
    )
    with pytest.raises(PipelineError) as exc_info:
        section_fetch.run_section_fetch_stage(manifest, settings, work_dir=tmp_path)
    assert "QATTA_ENABLE_URL_INGESTION" in str(exc_info.value)


def test_section_fetch_noop_for_local_files(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    manifest = QattaManifest(
        project_id="proj_local",
        source_path=str(tmp_path / "lecture.mp4"),
        duration_sec=60.0,
        candidates=[make_candidate("C_0001", 1_000, 10_000)],
    )
    result = section_fetch.run_section_fetch_stage(manifest, settings, work_dir=tmp_path)
    assert result.candidates[0].section_media_path is None
    assert not (tmp_path / "sections").exists()


# ---------------------------------------------------------------------------
# Pass 2 word alignment from a downloaded section
# ---------------------------------------------------------------------------


class SectionWordAdapter(fine_pass.TranscriptionAdapter):
    """Words in SECTION-LOCAL time; the pass must offset to absolute."""

    def __init__(self):
        self.received: list[tuple[int, int]] = []

    def transcribe_words(self, pcm, sr=16000, language=None, beam_size=2):
        # Section starts at 28_000 ms of the source timeline; utterance
        # sits ~1 s after the padded section head.
        self.received.append((int(audio_ms(pcm)), sr))
        return [
            WordTiming("الحلقة", 2_000, 2_400, 0.9),
            WordTiming("الجديدة", 2_500, 2_900, 0.8),
        ]


def audio_ms(pcm: np.ndarray) -> int:
    return int(round(len(pcm) * 1000 / SR))


def test_fine_pass_aligns_via_section_offset(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, fine_padding_ms=2000, snap_pad_ms=0)
    # Section file covers source [28_000, 34_000] -> 6 s local.
    section_pcm = np.zeros(6 * SR, dtype=np.float32)
    section_wav = write_wav(section_pcm, tmp_path / "C_0001_audio_16k.wav")
    manifest = QattaManifest(
        project_id="proj_sec",
        source_path="youtube:vid",
        duration_sec=100.0,
        transcript_source="youtube_subs_first",
        subtitle_path=str(tmp_path / "c.vtt"),
        atomic_utterances=[
            fast_pass.AtomicUtterance(
                u_id="U_0001", start_ms=29_000, end_ms=32_000, text="الحلقة الجديدة"
            ),
        ],
        candidates=[
            make_candidate(
                "C_0001",
                30_000,
                31_500,
                section_media=tmp_path / "C_0001.mp4",
                section_audio=section_wav,
                section_start=28_000,
            )
        ],
    )
    adapter = SectionWordAdapter()
    result = fine_pass.run_fine_alignment_stage(manifest, ["C_0001"], settings, adapter=adapter)

    candidate = result.candidates[0]
    # Snapped to absolute word bounds (offset 28_000 + local 2_000/2_900).
    assert candidate.start_ms == 30_000
    assert candidate.end_ms == 30_900
    words = result.atomic_utterances[0].words
    assert [w.word for w in words] == ["الحلقة", "الجديدة"]
    assert words[0].start_ms == 30_000 and words[0].end_ms == 30_400
    assert words[0].is_latin is False  # Arabic token
    # The adapter got the SECTION slice, not the full audio.
    assert adapter.received == [(6000, SR)]


def test_fine_pass_honest_note_when_section_missing(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    manifest = QattaManifest(
        project_id="proj_miss",
        source_path="youtube:vid",
        duration_sec=100.0,
        transcript_source="youtube_subs_first",
        subtitle_path=str(tmp_path / "c.vtt"),
        candidates=[
            make_candidate("C_0001", 30_000, 31_500)  # no sections
        ],
    )
    result = fine_pass.run_fine_alignment_stage(
        manifest, ["C_0001"], settings, adapter=SectionWordAdapter()
    )
    logs = " ".join(result.candidates[0].evidence_log)
    assert "no audio source" in logs
    assert result.candidates[0].start_ms == 30_000  # untouched


def test_fine_pass_requires_some_audio(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    manifest = QattaManifest(
        project_id="proj_none",
        source_path="youtube:vid",
        duration_sec=10.0,
        candidates=[make_candidate("C_0001", 1_000, 9_000)],
    )
    with pytest.raises(PipelineError) as exc_info:
        fine_pass.run_fine_alignment_stage(
            manifest, ["C_0001"], settings, adapter=SectionWordAdapter()
        )
    assert "No audio source" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Orchestrator: measured per-stage wall time
# ---------------------------------------------------------------------------


def test_orchestrator_records_stage_wall_time(tmp_path: Path) -> None:
    manifest_file = tmp_path / "qatta_manifest.json"
    manifest = QattaManifest(
        project_id="proj_time",
        source_path=str(tmp_path / "x.mp4"),
        duration_sec=5.0,
    )
    manifest_file.write_text(manifest.model_dump_json(), encoding="utf-8")
    orch = PipelineOrchestrator(
        project_id="proj_time",
        work_dir=tmp_path,
        settings=make_settings(tmp_path),
    )

    @orch.stage("s_dummy")
    def _dummy(m: QattaManifest) -> QattaManifest:
        return m

    report = orch.run_stage("s_dummy")
    orch.save_manifest()
    reloaded = orch.load_manifest()
    assert report["executed"] is True
    assert reloaded.stage_timings_ms["s_dummy"] >= 0
    persisted = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert "s_dummy" in persisted["stage_timings_ms"]
