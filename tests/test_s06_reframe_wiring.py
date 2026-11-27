"""Stage s06_reframe_subs wiring: opt-in, visible degradation, real trajectory.

The stage is where honesty is easiest to lose. Three rules are enforced here:

1. Face-guided framing is opt-in. With it off, no sampling happens at all —
   the stage must not quietly do expensive work because it can.
2. When it cannot run, the reason is recorded and the crop is centred. It
   never reports a detection it did not perform.
3. Timestamps land on the *source* timeline even when sampling a downloaded
   section, because the solver partitions the clip in source time.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from qatta.core.config import QattaSettings
from qatta.core.schema import (
    MAX_SCHEMA_VERSION,
    AtomicUtterance,
    ClipCandidate,
    CPSBreakdown,
    HookRemixVariant,
    QattaManifest,
    VetoGates,
    WordToken,
)
from qatta.stages.s06_reframe_subs import frame_sampler, run_reframe_subs_stage
from qatta.stages.s06_reframe_subs.camera_solver import BoundingBox, FaceDetection, FrameObservation
from qatta.stages.s06_reframe_subs.detector import NullDetector, observe_frames
from qatta.stages.s06_reframe_subs.frame_sampler import SampledFrame


def _manifest(tmp_path: Path, *, section_start_ms: int | None = None) -> QattaManifest:
    words = [
        WordToken(word="deploy", start_ms=1000, end_ms=1400, confidence=0.9, is_latin=True),
        WordToken(word="سريع", start_ms=1400, end_ms=1900, confidence=0.9, is_latin=False),
    ]
    source = tmp_path / "source.mp4"
    source.write_bytes(b"not real media, only existence is checked here")

    section_path = None
    if section_start_ms is not None:
        section = tmp_path / "section.mp4"
        section.write_bytes(b"section media")
        section_path = str(section)

    candidate = ClipCandidate(
        clip_id="clip_001",
        start_u_id="U_0001",
        end_u_id="U_0002",
        start_ms=3000,
        end_ms=7000,
        duration_sec=4.0,
        veto_gates=VetoGates(
            dangling_context=False,
            clean_audio_boundaries=True,
            crosstalk_ratio=0.0,
            passed_all=True,
        ),
        cps=CPSBreakdown(
            total_score=85.0,
            archetype="TACTICAL_INSIGHT",
            standalone_clarity=18.0,
            hook_strength=19.0,
            story_payoff=17.0,
            value_originality=16.0,
            audio_dynamics=15.0,
            boundary_precision=10.0,
        ),
        hook_remix=HookRemixVariant(enabled=False),
        section_media_path=section_path,
        section_start_ms=section_start_ms,
    )

    return QattaManifest(
        project_id="proj_wiring",
        source_path=str(source),
        duration_sec=10.0,
        atomic_utterances=[
            AtomicUtterance(
                u_id="U_0001",
                start_ms=1000,
                end_ms=1900,
                speaker="SPEAKER_00",
                text="deploy سريع",
                words=words,
            ),
            AtomicUtterance(
                u_id="U_0002",
                start_ms=2000,
                end_ms=7000,
                speaker="SPEAKER_00",
                text="كلام إضافي",
            ),
        ],
        candidates=[candidate],
        scene_cuts_ms=[],
    )


# ---------------------------------------------------------------------------
# Rule 1: opt-in means off is really off
# ---------------------------------------------------------------------------


def test_framing_off_does_no_sampling_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _explode(*args, **kwargs):
        raise AssertionError("sampling must not run while the feature is disabled")

    monkeypatch.setattr(frame_sampler.subprocess, "run", _explode)

    manifest = run_reframe_subs_stage(
        _manifest(tmp_path),
        settings=QattaSettings(face_guided_framing=False),
        captions_dir=tmp_path / "captions",
    )

    candidate = manifest.candidates[0]
    meta = candidate.framing_meta
    assert meta is not None
    assert meta.enabled is False
    assert meta.detector == "none"
    assert meta.frames_sampled == 0
    assert meta.frames_analysed == 0
    assert meta.degradation_reason is not None
    assert "disabled" in meta.degradation_reason
    # The trajectory still exists: a centred crop is a real result.
    assert candidate.crop_trajectory
    assert any("framing degraded" in line for line in candidate.evidence_log)


def test_a_v1_manifest_is_relabelled_when_it_gains_v2_fields(tmp_path: Path) -> None:
    """A rewritten manifest must not claim to be v1 while holding v2 fields.

    Otherwise a downgraded build reports "unknown field crop_trajectory"
    instead of the true cause: the file is newer than it understands.
    """
    manifest = _manifest(tmp_path)
    manifest.schema_version = 1

    updated = run_reframe_subs_stage(
        manifest,
        settings=QattaSettings(face_guided_framing=False),
        captions_dir=tmp_path / "captions",
    )

    assert updated.candidates[0].framing_meta is not None
    assert updated.schema_version == MAX_SCHEMA_VERSION == 2


def test_captions_are_written_to_their_own_namespace(tmp_path: Path) -> None:
    """The render stage owns {captions}/{clip}.ass; this stage must not clobber it."""
    captions = tmp_path / "captions"
    captions.mkdir()
    render_ass = captions / "clip_001.ass"
    render_ass.write_text("[Script Info]\n; render stage owns this\n", encoding="utf-8")

    manifest = run_reframe_subs_stage(
        _manifest(tmp_path),
        settings=QattaSettings(face_guided_framing=False),
        captions_dir=captions,
    )

    assert render_ass.read_text(encoding="utf-8").startswith("[Script Info]")
    reframe_ass = captions / "reframe" / "clip_001.ass"
    assert reframe_ass.is_file()
    assert manifest.candidates[0].rendered_paths["ass_captions"] == str(reframe_ass.resolve())


# ---------------------------------------------------------------------------
# Rule 2: an unavailable detector degrades visibly, never silently
# ---------------------------------------------------------------------------


def test_an_unavailable_detector_is_recorded_not_faked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "qatta.stages.s06_reframe_subs.detector_status",
        lambda: (False, "OpenCV (cv2) is not installed. Install the analysis extra."),
    )

    manifest = run_reframe_subs_stage(
        _manifest(tmp_path),
        settings=QattaSettings(face_guided_framing=True),
        captions_dir=tmp_path / "captions",
    )

    meta = manifest.candidates[0].framing_meta
    assert meta is not None
    assert meta.enabled is False
    assert meta.frames_sampled == 0
    assert meta.degradation_reason is not None
    assert "analysis extra" in meta.degradation_reason


def test_detector_none_is_an_explicit_choice_not_a_silent_skip(
    tmp_path: Path,
) -> None:
    manifest = run_reframe_subs_stage(
        _manifest(tmp_path),
        settings=QattaSettings(face_guided_framing=True, face_detector="none"),
        captions_dir=tmp_path / "captions",
    )

    meta = manifest.candidates[0].framing_meta
    assert meta is not None
    assert meta.detector == "none"
    assert meta.degradation_reason is not None
    assert "QATTA_FACE_DETECTOR" in meta.degradation_reason


def test_sampling_failure_degrades_that_clip_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A broken clip must not take the project's captions down with it."""
    monkeypatch.setattr("qatta.stages.s06_reframe_subs.detector_status", lambda: (True, None))

    # NullDetector would mean "not detecting", so use a non-null stand-in to
    # reach the sampling path this test is about.
    class _Detector:
        name = "opencv_haar"

        def detect(self, frame_bgr, timestamp_ms):  # noqa: ANN001, ARG002
            return FrameObservation(timestamp_ms=timestamp_ms, faces=[])

    monkeypatch.setattr(
        "qatta.stages.s06_reframe_subs.build_detector", lambda name="opencv_haar": _Detector()
    )
    monkeypatch.setattr(
        "qatta.stages.s06_reframe_subs.shutil.which", lambda name: "/usr/bin/ffmpeg"
    )

    def _boom(**kwargs):
        raise frame_sampler.FrameSamplingError("ffmpeg produced no frames for source.mp4")

    monkeypatch.setattr("qatta.stages.s06_reframe_subs.sample_frames", _boom)

    manifest = run_reframe_subs_stage(
        _manifest(tmp_path),
        settings=QattaSettings(face_guided_framing=True),
        captions_dir=tmp_path / "captions",
    )

    candidate = manifest.candidates[0]
    assert candidate.framing_meta is not None
    assert candidate.framing_meta.enabled is False
    assert "Frame sampling failed" in (candidate.framing_meta.degradation_reason or "")
    # Captions still produced: the rest of the stage kept working.
    assert (tmp_path / "captions" / "reframe" / "clip_001.ass").is_file()


# ---------------------------------------------------------------------------
# Rule 3: source-timeline rebasing, and the trajectory actually reflects faces
# ---------------------------------------------------------------------------


def test_section_media_timestamps_are_rebased_onto_the_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sampling a section must ask for section-relative time, then rebase back."""
    seen: dict = {}

    class _Detector:
        name = "opencv_haar"

        def detect(self, frame_bgr, timestamp_ms):  # noqa: ANN001
            # A face on the left of frame, so the solved centre must move there.
            return FrameObservation(
                timestamp_ms=timestamp_ms,
                faces=[
                    FaceDetection(
                        bbox=BoundingBox(x_min=0.1, y_min=0.1, x_max=0.3, y_max=0.4),
                        face_id=0,
                    )
                ],
            )

    def _fake_sample(**kwargs):
        seen.update(kwargs)
        # Timestamps are relative to the SECTION file, which starts at 1000 ms.
        return [
            SampledFrame(path=Path("/nonexistent/frame_00001.jpg"), timestamp_ms=2000),
            SampledFrame(path=Path("/nonexistent/frame_00002.jpg"), timestamp_ms=2200),
        ]

    monkeypatch.setattr("qatta.stages.s06_reframe_subs.detector_status", lambda: (True, None))
    monkeypatch.setattr(
        "qatta.stages.s06_reframe_subs.build_detector", lambda name="opencv_haar": _Detector()
    )
    monkeypatch.setattr(
        "qatta.stages.s06_reframe_subs.shutil.which", lambda name: "/usr/bin/ffmpeg"
    )
    monkeypatch.setattr("qatta.stages.s06_reframe_subs.sample_frames", _fake_sample)
    monkeypatch.setattr(
        "qatta.stages.s06_reframe_subs.observe_frames",
        lambda detector, frames: [detector.detect(object(), f.timestamp_ms) for f in frames],
    )

    manifest = run_reframe_subs_stage(
        _manifest(tmp_path, section_start_ms=1000),
        settings=QattaSettings(face_guided_framing=True),
        captions_dir=tmp_path / "captions",
    )

    # The clip is 3000..7000 in source time; the section starts at 1000, so the
    # sampler must be asked for 2000..6000 in the section's own timeline.
    assert seen["start_ms"] == 2000
    assert seen["end_ms"] == 6000
    assert seen["input_path"] == tmp_path / "section.mp4"

    meta = manifest.candidates[0].framing_meta
    assert meta is not None
    assert meta.enabled is True
    assert meta.detector == "opencv_haar"
    assert meta.frames_sampled == 2
    assert meta.frames_analysed == 2
    assert meta.frames_with_face == 2
    assert meta.degradation_reason is None

    # Keyframes are in SOURCE time (3000..7000), never 2000..2200.
    keyframes = [k for shot in manifest.candidates[0].crop_trajectory for k in shot.keyframes]
    assert keyframes
    assert all(3000 <= k.timestamp_ms <= 7000 for k in keyframes), keyframes


# ---------------------------------------------------------------------------
# observe_frames: decoding is a boundary, so it is injectable
# ---------------------------------------------------------------------------


def test_observe_frames_skips_frames_that_do_not_decode() -> None:
    frames = [
        SampledFrame(path=Path("/a.jpg"), timestamp_ms=0),
        SampledFrame(path=Path("/b.jpg"), timestamp_ms=200),
        SampledFrame(path=Path("/c.jpg"), timestamp_ms=400),
    ]
    unreadable = Path("/b.jpg")

    observations = observe_frames(
        NullDetector(),
        frames,
        reader=lambda path: None if path == unreadable else object(),
    )

    # b.jpg is skipped rather than aborting the clip; callers must not assume
    # frames_analysed == frames_sampled.
    assert [obs.timestamp_ms for obs in observations] == [0, 400]


def test_observe_frames_reports_nothing_for_the_null_detector() -> None:
    frames = [SampledFrame(path=Path("/a.jpg"), timestamp_ms=0)]

    observations = observe_frames(NullDetector(), frames, reader=lambda path: object())

    assert len(observations) == 1
    assert observations[0].faces == []
