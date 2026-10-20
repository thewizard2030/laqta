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
from pathlib import Path
from typing import TYPE_CHECKING

from qatta.core.config import QattaSettings
from qatta.core.schema import QattaManifest, WordToken
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

if TYPE_CHECKING:
    from qatta.core.pipeline import PipelineOrchestrator

logger = logging.getLogger("qatta.s06_reframe_subs")

__all__ = [
    "ASSCaptionConfig",
    "ArabicBiDiShaper",
    "BoundingBox",
    "CameraSolver",
    "CaptionLine",
    "FaceDetection",
    "FrameObservation",
    "LayoutMode",
    "LayoutStateMachine",
    "SceneAwareHysteresisSolver",
    "ShotSegment",
    "compute_mouth_aspect_ratio",
    "generate_dynamic_ass",
    "group_words_into_lines",
    "hex_to_ass_color",
    "ms_to_ass_time",
    "partition_clip_into_shots",
    "register",
    "run_reframe_subs_stage",
]


def run_reframe_subs_stage(
    manifest: QattaManifest,
    settings: QattaSettings | None = None,
    captions_dir: Path | None = None,
) -> QattaManifest:
    """Execute Stage s06 permissive reframing and Arabic BiDi caption generation."""
    settings = settings or QattaSettings()
    out_dir = captions_dir or settings.manifest_path(manifest.project_id).parent / "captions"
    out_dir.mkdir(parents=True, exist_ok=True)

    camera_solver = CameraSolver(
        frame_width=manifest.video_width or 1920,
        frame_height=manifest.video_height or 1080,
    )

    for candidate in manifest.candidates:
        # 1. Camera Solver & Scene-Aware Trajectory
        shots = camera_solver.solve_clip(
            clip_start_ms=candidate.start_ms,
            clip_end_ms=candidate.end_ms,
            scene_cuts_ms=manifest.scene_cuts_ms,
        )

        candidate.evidence_log.append(
            f"s06_reframe_subs: Solved {len(shots)} shots for clip '{candidate.clip_id}'"
        )
        for s in shots:
            candidate.evidence_log.append(
                f"  shot_{s.shot_index} [{s.start_ms}ms..{s.end_ms}ms]: layout={s.layout.value}"
            )

        # 2. Extract constituent words for candidate span
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

        # 3. Group into lines and generate dynamic ASS subtitles
        lines = group_words_into_lines(candidate_words)
        ass_content = generate_dynamic_ass(lines)

        ass_path = out_dir / f"{candidate.clip_id}.ass"
        ass_path.write_text(ass_content, encoding="utf-8")
        candidate.rendered_paths["ass_captions"] = str(ass_path.resolve())

    return manifest


def register(orchestrator: PipelineOrchestrator) -> None:
    """Attach s06_reframe_subs to a PipelineOrchestrator."""

    @orchestrator.stage("s06_reframe_subs")
    def _stage(manifest: QattaManifest) -> QattaManifest:
        return run_reframe_subs_stage(manifest, orchestrator.settings)
