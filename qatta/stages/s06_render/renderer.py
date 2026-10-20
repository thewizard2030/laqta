"""Stage s06_render — ASS Subtitle Generation & 9:16 Vertical Video Rendering.

Accepts a QattaManifest, generates styled ASS/SRT captions for the candidate's
boundaries (using WordToken timings if available from stage s02b, otherwise
coarse AtomicUtterance bounds), constructs safe FFmpeg argument arrays for
vertical 9:16 rendering, executes rendering, validates the output with ffprobe,
and records the resulting path into ``candidate.rendered_paths["vertical_9_16"]``.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path

from qatta.core.config import QattaSettings
from qatta.core.pipeline import PipelineError
from qatta.core.schema import AtomicUtterance, QattaManifest


def _require_ffmpeg(timeout: float = 10.0) -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise PipelineError(
            "ffmpeg binary was not found on PATH. Install ffmpeg to run "
            "stage s06_render (e.g. 'sudo dnf install ffmpeg' on Fedora)."
        )
    return ffmpeg


def _require_ffprobe(timeout: float = 10.0) -> str:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise PipelineError(
            "ffprobe binary was not found on PATH. Install ffmpeg/ffprobe to run stage s06_render."
        )
    return ffprobe


def utterances_to_segments(utterances: list[AtomicUtterance]):
    """Convert core AtomicUtterance objects to the schema used by caption services."""
    from app.schemas.transcription import TranscriptSegment, WordTiming

    segments = []
    for idx, u in enumerate(utterances, start=1):
        words = [
            WordTiming(
                word=w.word,
                start=w.start_ms / 1000.0,
                end=w.end_ms / 1000.0,
                probability=w.confidence,
            )
            for w in u.words
        ]
        segments.append(
            TranscriptSegment(
                id=str(idx),
                start=u.start_ms / 1000.0,
                end=u.end_ms / 1000.0,
                text=u.text,
                words=words,
            )
        )
    return segments


def run_render_stage(
    manifest: QattaManifest,
    candidate_id: str | None = None,
    settings: QattaSettings | None = None,
    work_dir: Path | None = None,
    quality: str = "high",
    layout: str = "fill_crop",
    burn_captions: bool = True,
    cancel_event: asyncio.Event | None = None,
) -> QattaManifest:
    """Execute Stage s06 rendering on selected candidate(s).

    Updates manifest in-place (and returns it) with:
    ``candidate.rendered_paths["vertical_9_16"] = str(output_path)``.
    """
    settings = settings or QattaSettings()
    ffmpeg_bin = _require_ffmpeg(settings.ffmpeg_timeout_seconds)
    _require_ffprobe(settings.ffprobe_timeout_seconds)

    source_path = Path(manifest.source_path)

    # Determine project directory
    if work_dir is None:
        work_dir = Path(settings.manifest_path(manifest.project_id).parent)
    renders_dir = work_dir / "renders"
    captions_dir = work_dir / "captions"
    renders_dir.mkdir(parents=True, exist_ok=True)
    captions_dir.mkdir(parents=True, exist_ok=True)

    # Select candidate(s) to render
    if candidate_id:
        targets = [c for c in manifest.candidates if c.clip_id == candidate_id]
        if not targets:
            raise PipelineError(f"Candidate '{candidate_id}' not found in manifest.")
    else:
        # Default: render candidates that passed veto gates (or top scoring)
        targets = [c for c in manifest.candidates if c.veto_gates.passed_all]
        if not targets and manifest.candidates:
            targets = [manifest.candidates[0]]

    # YouTube captions-first flow: candidates carry their own downloaded
    # section media, so the (absent) full source is not required.
    if not source_path.is_file() and not any(c.section_media_path for c in targets):
        raise PipelineError(f"Source media does not exist: {source_path}")

    if not targets:
        return manifest

    # Convert utterances to segment schema for caption generator
    segments = utterances_to_segments(manifest.atomic_utterances)

    from app.schemas.captions import CaptionStyleSettings
    from app.services.captions.service import generate_candidate_captions
    from app.services.rendering.render import (
        build_render_command,
        probe_render_environment,
        probe_render_output,
    )

    env_report = probe_render_environment(ffmpeg_bin)
    h264_enc = env_report.get("h264_encoder") or "libx264"

    src_w = manifest.video_width or 1920
    src_h = manifest.video_height or 1080

    for candidate in targets:
        clip_id = candidate.clip_id
        duration_ms = candidate.end_ms - candidate.start_ms

        # Per-candidate media: prefer the small downloaded section
        # (captions-first flow) and REBASE the clip timestamps onto the
        # section timeline; otherwise cut from the full source.
        section_offset = candidate.section_start_ms or 0
        if candidate.section_media_path and Path(candidate.section_media_path).is_file():
            clip_input = Path(candidate.section_media_path)
            clip_start_ms = candidate.start_ms - section_offset
            clip_end_ms = candidate.end_ms - section_offset
        else:
            clip_input = source_path
            clip_start_ms = candidate.start_ms
            clip_end_ms = candidate.end_ms

        caption_path = None
        caption_format = "ass"
        if burn_captions and segments:
            has_word_timings = any(bool(u.words) for u in manifest.atomic_utterances)
            style = CaptionStyleSettings(
                karaoke=has_word_timings,
            )
            captions_res = generate_candidate_captions(
                captions_dir=captions_dir,
                candidate_id=clip_id,
                start_ms=clip_start_ms,
                end_ms=clip_end_ms,
                segments=segments,
                style=style,
                formats=("ass", "srt"),
            )
            caption_path = captions_res.ass_path

        out_name = f"{clip_id}_{quality}.mp4"
        out_path = renders_dir / out_name
        tmp_path = renders_dir / f".{out_name}.part-{os.getpid()}"

        cmd = build_render_command(
            ffmpeg_bin=ffmpeg_bin,
            input_path=clip_input,
            output_path=tmp_path,
            layout=layout,
            quality=quality,
            src_width=src_w,
            src_height=src_h,
            has_audio=True,
            caption_path=caption_path,
            caption_format=caption_format,
            start_ms=clip_start_ms,
            duration_ms=duration_ms,
            video_encoder=h264_enc,
        )

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=settings.ffmpeg_timeout_seconds,
                check=False,
            )
            if proc.returncode != 0:
                raise PipelineError(
                    f"FFmpeg render failed for clip '{clip_id}' (code {proc.returncode}): "
                    f"{(proc.stderr or '')[-500:]}"
                )
            if not tmp_path.exists() or tmp_path.stat().st_size == 0:
                raise PipelineError(f"Render produced empty file for clip '{clip_id}'.")

            # Probe output validation
            probe_res = probe_render_output(tmp_path)
            if not probe_res.get("valid"):
                err_msg = probe_res.get("error")
                raise PipelineError(
                    f"Rendered output validation failed for clip '{clip_id}': {err_msg}"
                )

            # Atomic replace
            os.replace(tmp_path, out_path)
            candidate.rendered_paths["vertical_9_16"] = str(out_path.resolve())

        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    return manifest


def register(orchestrator, candidate_id: str | None = None) -> None:
    """Attach s06_render to a PipelineOrchestrator."""

    @orchestrator.stage("s06_render")
    def _stage(manifest: QattaManifest) -> QattaManifest:
        return run_render_stage(
            manifest,
            candidate_id=candidate_id,
            settings=orchestrator.settings,
            work_dir=orchestrator.work_dir,
        )
