"""Stage s06_reframe_subs — Permissive CV Reframing & Arabic BiDi ASS Subtitles.

Pipeline stage providing:
- Fast 5 FPS sampling on winning candidates with face & MAR detection.
- Scene-Aware Hysteresis Deadband camera reframing (0% pan inside deadband,
  instant snap across scene cuts).
- Dynamic layout state machine (SINGLE_SPEAKER, DUAL_SPLIT, SCREENSHARE_PIP).
- ArabicBiDiShaper with First Strong Isolates (\u2068...\u2069) and RLM (\u200f).
- Dynamic word-level highlight ASS subtitle generation.
"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING

from qatta.core.config import QattaSettings
from qatta.core.schema import (
    MAX_SCHEMA_VERSION,
    ClipCandidate,
    CropKeyframe,
    FramingMeta,
    QattaManifest,
    ShotFraming,
    WordToken,
)
from qatta.stages.s06_reframe_subs.arabic_ass import (
    ArabicBiDiShaper,
    ASSCaptionConfig,
    CaptionLine,
    generate_dynamic_ass,
    group_words_into_lines,
    hex_to_ass_color,
    ms_to_ass_time,
)
from qatta.stages.s06_reframe_subs.camera_solver import (
    BoundingBox,
    CameraSolver,
    FaceDetection,
    FrameObservation,
    LayoutMode,
    LayoutStateMachine,
    SceneAwareHysteresisSolver,
    ShotSegment,
    compute_mouth_aspect_ratio,
    partition_clip_into_shots,
)
from qatta.stages.s06_reframe_subs.detector import (
    DetectorUnavailableError,
    FaceDetector,
    NullDetector,
    OpenCVHaarDetector,
    build_detector,
    detector_status,
    observe_frames,
)
from qatta.stages.s06_reframe_subs.frame_sampler import (
    FrameSamplingError,
    SampledFrame,
    SamplingCancelledError,
    build_sample_command,
    sample_frames,
    temporary_sample_dir,
)

if TYPE_CHECKING:
    from qatta.core.pipeline import PipelineOrchestrator

logger = logging.getLogger("qatta.s06_reframe_subs")

__all__ = [
    "ASSCaptionConfig",
    "ArabicBiDiShaper",
    "BoundingBox",
    "CameraSolver",
    "CaptionLine",
    "DetectorUnavailableError",
    "FaceDetection",
    "FaceDetector",
    "FrameObservation",
    "FrameSamplingError",
    "LayoutMode",
    "LayoutStateMachine",
    "NullDetector",
    "OpenCVHaarDetector",
    "SampledFrame",
    "SamplingCancelledError",
    "SceneAwareHysteresisSolver",
    "ShotSegment",
    "build_detector",
    "build_sample_command",
    "compute_mouth_aspect_ratio",
    "detector_status",
    "generate_dynamic_ass",
    "group_words_into_lines",
    "hex_to_ass_color",
    "ms_to_ass_time",
    "observe_frames",
    "partition_clip_into_shots",
    "register",
    "run_reframe_subs_stage",
    "sample_frames",
    "temporary_sample_dir",
]


def _candidate_media(manifest: QattaManifest, candidate: ClipCandidate) -> tuple[Path | None, int]:
    """Return the file to sample and the offset that maps it to source time.

    Mirrors the renderer's rule: prefer the small downloaded section from the
    captions-first flow, where ``t=0`` in that file is ``section_start_ms`` in
    the source. Getting this wrong does not crash — it silently samples the
    wrong part of the video, which is worse.
    """
    if candidate.section_media_path:
        section = Path(candidate.section_media_path)
        if section.is_file():
            return section, candidate.section_start_ms or 0
    source = Path(manifest.source_path)
    return (source if source.is_file() else None), 0


def _select_detector(settings: QattaSettings) -> tuple[FaceDetector, str | None]:
    """Pick the detector, and say plainly why it is the null one if it is.

    Never raises: a missing detector is a degraded result the stage records,
    not a reason to fail a project whose captions and crop still work.
    """
    if not settings.face_guided_framing:
        return NullDetector(), (
            "Face-guided framing is disabled (QATTA_FACE_GUIDED_FRAMING=false); "
            "the crop stays centred."
        )
    if settings.face_detector == "none":
        return NullDetector(), (
            "QATTA_FACE_DETECTOR is 'none'; no detection runs and the crop stays centred."
        )

    available, reason = detector_status()
    if not available:
        return NullDetector(), reason

    try:
        return build_detector(settings.face_detector), None
    except DetectorUnavailableError as exc:
        return NullDetector(), exc.reason


def _rebase(frames: list[SampledFrame], offset_ms: int) -> list[SampledFrame]:
    """Shift media-relative timestamps back onto the source timeline.

    The solver partitions the clip using source-time spans, so an observation
    left on the section's own timeline would land in the wrong shot — or
    outside every shot, which looks like "no face found".
    """
    if offset_ms == 0:
        return frames
    return [
        SampledFrame(path=frame.path, timestamp_ms=frame.timestamp_ms + offset_ms)
        for frame in frames
    ]


def run_reframe_subs_stage(
    manifest: QattaManifest,
    settings: QattaSettings | None = None,
    captions_dir: Path | None = None,
) -> QattaManifest:
    """Solve crop trajectories and write Arabic BiDi ASS captions per clip.

    Face-guided framing is opt-in and degrades visibly: when it is off, when
    the detector is unavailable, or when sampling fails, the stage records the
    real reason in ``framing_meta.degradation_reason`` and still produces a
    usable (centred) trajectory. Nothing here claims a capability it did not
    exercise.
    """
    settings = settings or QattaSettings()
    out_dir = captions_dir or settings.manifest_path(manifest.project_id).parent / "captions"
    # Sampling scratch space belongs next to the captions, not in the user's
    # data dir: a caller that passes its own captions_dir (tests, the API)
    # must not cause writes somewhere it did not choose.
    temp_base = out_dir.parent
    # Namespaced on purpose: the render stage writes ``{captions_dir}/{clip}.ass``
    # with its own styled cues. Sharing a filename meant whichever stage ran
    # last silently replaced the other's subtitles.
    reframe_dir = out_dir / "reframe"
    reframe_dir.mkdir(parents=True, exist_ok=True)

    detector, detector_reason = _select_detector(settings)
    detecting = not isinstance(detector, NullDetector)
    ffmpeg_bin = shutil.which("ffmpeg") if detecting else None
    if detecting and ffmpeg_bin is None:
        detecting = False
        detector_reason = (
            "ffmpeg was not found on PATH, so frames could not be sampled; the crop stays centred."
        )

    camera_solver = CameraSolver(
        frame_width=manifest.video_width or 1920,
        frame_height=manifest.video_height or 1080,
    )

    for candidate in manifest.candidates:
        # 1. Optional face observation, bounded to this clip.
        started = time.monotonic()
        observations: list[FrameObservation] = []
        sampled = 0
        degradation = detector_reason

        if detecting:
            media_path, offset_ms = _candidate_media(manifest, candidate)
            if media_path is None:
                degradation = (
                    f"Source media for '{candidate.clip_id}' is missing, so frames "
                    "could not be sampled; the crop stays centred."
                )
            else:
                try:
                    with temporary_sample_dir(temp_base) as frames_dir:
                        frames = sample_frames(
                            ffmpeg_bin=ffmpeg_bin,
                            input_path=media_path,
                            out_dir=frames_dir,
                            start_ms=max(0, candidate.start_ms - offset_ms),
                            end_ms=max(1, candidate.end_ms - offset_ms),
                            fps=settings.reframe_sample_fps,
                            max_frames=settings.reframe_max_frames,
                            timeout_seconds=settings.reframe_timeout_seconds,
                        )
                        sampled = len(frames)
                        observations = observe_frames(detector, _rebase(frames, offset_ms))
                except FrameSamplingError as exc:
                    # One clip's sampling failure must not sink the project.
                    degradation = f"Frame sampling failed for '{candidate.clip_id}': {exc}"

        # 2. Solve the trajectory, now with real observations when we have them.
        shots = camera_solver.solve_clip(
            clip_start_ms=candidate.start_ms,
            clip_end_ms=candidate.end_ms,
            scene_cuts_ms=manifest.scene_cuts_ms,
            observations=observations,
        )

        candidate.evidence_log.append(
            f"s06_reframe_subs: Solved {len(shots)} shots for clip '{candidate.clip_id}'"
        )
        for s in shots:
            candidate.evidence_log.append(
                f"  shot_{s.shot_index} [{s.start_ms}ms..{s.end_ms}ms]: layout={s.layout.value}"
            )

        # 3. Persist the solved trajectory (not the raw observations).
        candidate.crop_trajectory = [
            ShotFraming(
                shot_index=shot.shot_index,
                start_ms=shot.start_ms,
                end_ms=shot.end_ms,
                layout=shot.layout.value,
                keyframes=[
                    # The solver clamps internally; clamp again so a future
                    # solver change cannot make the manifest invalid and take
                    # the whole project down over a framing detail.
                    CropKeyframe(timestamp_ms=ts, center_x=min(1.0, max(0.0, center)))
                    for ts, center in shot.crop_trajectory
                ],
            )
            for shot in shots
        ]
        candidate.framing_meta = FramingMeta(
            detector=detector.name,
            enabled=detecting and degradation is None,
            frames_sampled=sampled,
            frames_analysed=len(observations),
            frames_with_face=sum(1 for obs in observations if obs.faces),
            elapsed_ms=int(round((time.monotonic() - started) * 1000)),
            degradation_reason=degradation,
        )
        if degradation:
            candidate.evidence_log.append(f"s06_reframe_subs: framing degraded — {degradation}")

        # 4. Extract constituent words for the candidate span.
        candidate_words: list[WordToken] = []
        for u in manifest.atomic_utterances:
            if candidate.start_ms <= u.start_ms and u.end_ms <= candidate.end_ms:
                if u.words:
                    candidate_words.extend(u.words)
                else:
                    # Synthesize token from utterance text if word tokens are not present
                    candidate_words.append(
                        WordToken(
                            word=u.text,
                            start_ms=u.start_ms,
                            end_ms=u.end_ms,
                            confidence=1.0,
                            is_latin=bool(ArabicBiDiShaper.LATIN_NUM_PATTERN.search(u.text)),
                        )
                    )

        # 5. Group into lines and generate dynamic ASS subtitles.
        lines = group_words_into_lines(candidate_words)
        ass_content = generate_dynamic_ass(lines)

        ass_path = reframe_dir / f"{candidate.clip_id}.ass"
        ass_path.write_text(ass_content, encoding="utf-8")
        candidate.rendered_paths["ass_captions"] = str(ass_path.resolve())

    # The manifest now carries v2 fields, so it must say so. Leaving a
    # rewritten v1 file labelled v1 would make an older build fail strict
    # validation ("unknown field crop_trajectory") instead of reporting the
    # real cause: this manifest is newer than that build understands.
    manifest.schema_version = MAX_SCHEMA_VERSION
    return manifest


def register(orchestrator: PipelineOrchestrator) -> None:
    """Attach s06_reframe_subs to a PipelineOrchestrator."""

    @orchestrator.stage("s06_reframe_subs")
    def _stage(manifest: QattaManifest) -> QattaManifest:
        return run_reframe_subs_stage(manifest, orchestrator.settings)
