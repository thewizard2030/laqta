"""Stage s07_render_learn — YPP-Safe FFmpeg 9:16 Shorts Renderer & Hook Remix.

Features:
- Single-pass FFmpegFilterGraphBuilder compiling:
  * Dynamic crop coordinates (or vstack for DUAL_SPLIT / SCREENSHARE_PIP).
  * Pattern Interrupt Zoom (1.12x punch-in zoom on audio_rms_norm > 0.80 or climax).
  * B-Roll / Text Card callout overlays in upper half of frame (visual transformation).
  * Subtitle burn-in via Arabic .ass filter.
  * Audio normalization (loudnorm=I=-14:TP=-1.5:LRA=11) and micro-silence trimming.
- Hook Remix dual rendering (original chronological cut + hook-first cut with transition flash).
- MonetizationMeta.visual_transformation_ratio calculation (flags warning if < 0.35).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from qatta.core.config import QattaSettings
from qatta.core.schema import (
    AtomicUtterance,
    BrollCue,
    ClipCandidate,
    MonetizationMeta,
    QattaManifest,
)
from qatta.stages.s06_reframe_subs.camera_solver import (
    CameraSolver,
    LayoutMode,
    ShotSegment,
)

logger = logging.getLogger("qatta.s07_renderer")


@dataclass
class PunchZoomInterval:
    """A timed punch-in zoom window."""

    start_sec: float
    end_sec: float
    zoom_factor: float = 1.12
    reason: str = "audio_rms_norm"


def escape_ffmpeg_filter_path(path: str | Path) -> str:
    """Escape a filesystem path for FFmpeg filter arguments."""
    p = str(path).replace("\\", "/")
    return (
        p.replace("'", r"\'")
        .replace(":", r"\:")
        .replace(",", r"\,")
        .replace("[", r"\[")
        .replace("]", r"\]")
    )


def detect_punch_in_zooms(
    candidate: ClipCandidate,
    utterances: list[AtomicUtterance],
    rms_threshold: float = 0.80,
    zoom_factor: float = 1.12,
) -> list[PunchZoomInterval]:
    """Identify punch-in zoom intervals for high RMS or climax utterances."""
    # Find utterances inside candidate span
    clip_utts = [
        u for u in utterances if candidate.start_ms <= u.start_ms and u.end_ms <= candidate.end_ms
    ]
    if not clip_utts:
        return []

    zooms: list[PunchZoomInterval] = []

    # 1. High RMS utterances
    for u in clip_utts:
        if u.audio_rms_norm >= rms_threshold:
            start_sec = max(0.0, (u.start_ms - candidate.start_ms) / 1000.0)
            end_sec = min(candidate.duration_sec, (u.end_ms - candidate.start_ms) / 1000.0)
            if end_sec > start_sec:
                zooms.append(
                    PunchZoomInterval(
                        start_sec=start_sec,
                        end_sec=end_sec,
                        zoom_factor=zoom_factor,
                        reason=f"rms={u.audio_rms_norm:.2f}",
                    )
                )

    # 2. Climax utterance (if not already zoomed)
    # Intensity metric combines audio_rms_norm and pitch_variance
    climax_utt = max(
        clip_utts,
        key=lambda u: (u.audio_rms_norm or 0.0) + (u.pitch_variance or 0.0),
    )
    climax_start = max(0.0, (climax_utt.start_ms - candidate.start_ms) / 1000.0)
    climax_end = min(candidate.duration_sec, (climax_utt.end_ms - candidate.start_ms) / 1000.0)

    already_covered = any(z.start_sec <= climax_start and climax_end <= z.end_sec for z in zooms)
    if not already_covered and climax_end > climax_start:
        zooms.append(
            PunchZoomInterval(
                start_sec=climax_start,
                end_sec=climax_end,
                zoom_factor=zoom_factor,
                reason="climax_utterance",
            )
        )

    # Sort and deduplicate/merge overlapping zooms
    zooms.sort(key=lambda z: z.start_sec)
    merged: list[PunchZoomInterval] = []
    for z in zooms:
        if not merged:
            merged.append(z)
        else:
            prev = merged[-1]
            if z.start_sec <= prev.end_sec:
                merged[-1] = PunchZoomInterval(
                    start_sec=prev.start_sec,
                    end_sec=max(prev.end_sec, z.end_sec),
                    zoom_factor=zoom_factor,
                    reason=f"{prev.reason}+{z.reason}",
                )
            else:
                merged.append(z)

    return merged


def compute_visual_transformation_ratio(
    candidate: ClipCandidate,
    shots: list[ShotSegment],
    zooms: list[PunchZoomInterval],
    broll_cues: list[BrollCue],
) -> float:
    """Calculate the ratio of candidate timeline containing visual transformations.

    Transformations include:
    - Split-screen (DUAL_SPLIT) or Picture-in-Picture (SCREENSHARE_PIP) layout shots.
    - Pattern Interrupt Zooms.
    - B-roll cues and Callout Text Card overlays.
    - Non-centered crop panning shifts.
    """
    total_sec = candidate.duration_sec
    if total_sec <= 0:
        return 0.0

    intervals: list[tuple[float, float]] = []

    # 1. Layout transformations (DUAL_SPLIT or SCREENSHARE_PIP)
    for s in shots:
        if s.layout in (LayoutMode.DUAL_SPLIT, LayoutMode.SCREENSHARE_PIP):
            t_start = max(0.0, (s.start_ms - candidate.start_ms) / 1000.0)
            t_end = min(total_sec, (s.end_ms - candidate.start_ms) / 1000.0)
            if t_end > t_start:
                intervals.append((t_start, t_end))

    # 2. Punch-in zooms
    for z in zooms:
        intervals.append((max(0.0, z.start_sec), min(total_sec, z.end_sec)))

    # 3. B-Roll and Callout text cards
    for cue in broll_cues:
        t_start = max(0.0, (cue.trigger_ms - candidate.start_ms) / 1000.0)
        t_end = min(total_sec, t_start + (cue.duration_ms / 1000.0))
        if t_end > t_start:
            intervals.append((t_start, t_end))

    # 4. Significant crop panning shifts
    for s in shots:
        if s.layout == LayoutMode.SINGLE_SPEAKER:
            # Check if trajectory pans away from middle 0.50 by > 0.05
            panned_samples = [
                t_ms for (t_ms, center_x) in s.crop_trajectory if abs(center_x - 0.50) > 0.05
            ]
            if panned_samples:
                t_start = max(0.0, (min(panned_samples) - candidate.start_ms) / 1000.0)
                t_end = min(total_sec, (max(panned_samples) - candidate.start_ms) / 1000.0)
                if t_end > t_start:
                    intervals.append((t_start, t_end))

    if not intervals:
        return 0.0

    # Merge intervals and sum union duration
    intervals.sort(key=lambda iv: iv[0])
    merged: list[tuple[float, float]] = []
    for start, end in intervals:
        if not merged:
            merged.append((start, end))
        else:
            prev_start, prev_end = merged[-1]
            if start <= prev_end:
                merged[-1] = (prev_start, max(prev_end, end))
            else:
                merged.append((start, end))

    transformed_sec = sum(end - start for start, end in merged)
    ratio = min(1.0, max(0.0, transformed_sec / total_sec))
    return round(ratio, 3)


class FFmpegFilterGraphBuilder:
    """Builds single-pass FFmpeg filtergraphs for 9:16 vertical shorts."""

    def __init__(
        self,
        target_width: int = 1080,
        target_height: int = 1920,
    ) -> None:
        self.target_width = target_width
        self.target_height = target_height

    def build_crop_filter(
        self,
        layout: LayoutMode,
        zooms: list[PunchZoomInterval] | None = None,
    ) -> str:
        """Build video filtering chain for vertical reframing and punch zooms."""
        out_w = self.target_width
        out_h = self.target_height
        zooms = zooms or []

        # Zoom expression if punch zooms exist
        if zooms:
            zoom_conds = [f"between(t,{z.start_sec:.2f},{z.end_sec:.2f})" for z in zooms]
            combined_cond = "+".join(zoom_conds)
            zoom_factor = zooms[0].zoom_factor
            zoom_w_expr = f"if({combined_cond},iw/{zoom_factor:.2f},iw)"
            zoom_h_expr = f"if({combined_cond},ih/{zoom_factor:.2f},ih)"
            zoom_filter = (
                f"crop=w='{zoom_w_expr}':h='{zoom_h_expr}':x='(iw-ow)/2':y='(ih-oh)/2',"
                f"scale={out_w}:{out_h}"
            )
        else:
            zoom_filter = f"scale={out_w}:{out_h}"

        if layout == LayoutMode.SINGLE_SPEAKER:
            # 9:16 vertical center crop and scale
            base = (
                f"crop=w='min(iw,ih*9/16)':h='min(ih,iw*16/9)':x='(iw-ow)/2':y='(ih-oh)/2',"
                f"{zoom_filter}"
            )
            return base

        if layout == LayoutMode.DUAL_SPLIT:
            # Top half 1080x960, bottom half 1080x960, vstack
            half_h = out_h // 2
            top = (
                f"split=2[top_in][bot_in];"
                f"[top_in]crop=w='min(iw,ih*9/8)':h='ih':x=0:y=0,scale={out_w}:{half_h}[top_out];"
                f"[bot_in]crop=w='min(iw,ih*9/8)':h='ih':x='iw-ow':y=0,scale={out_w}:{half_h}[bot_out];"
                f"[top_out][bot_out]vstack=inputs=2"
            )
            return top

        if layout == LayoutMode.SCREENSHARE_PIP:
            # Top 60% slide/content (1080x1152), bottom 40% face (1080x768), vstack
            top_h = int(out_h * 0.60)
            bot_h = out_h - top_h
            pip = (
                f"split=2[scr_in][fac_in];"
                f"[scr_in]scale={out_w}:{top_h}:force_original_aspect_ratio=decrease,"
                f"pad={out_w}:{top_h}:(ow-iw)/2:(oh-ih)/2[scr_out];"
                f"[fac_in]crop=w='min(iw,ih*4/3)':h='ih':x='(iw-ow)/2':y='(ih-oh)/2',"
                f"scale={out_w}:{bot_h}[fac_out];"
                f"[scr_out][fac_out]vstack=inputs=2"
            )
            return pip

        return f"scale={out_w}:{out_h}"

    def build_broll_overlay_filter(
        self,
        broll_cues: list[BrollCue],
        clip_start_ms: int,
        clip_duration_sec: float,
    ) -> list[str]:
        """Construct callout text card and B-roll overlay filters in upper half of frame."""
        filters: list[str] = []
        for cue in broll_cues:
            t_start = max(0.0, (cue.trigger_ms - clip_start_ms) / 1000.0)
            t_end = min(clip_duration_sec, t_start + (cue.duration_ms / 1000.0))
            if t_end <= t_start:
                continue

            # Upper half positioning (y=200..380) with centered card
            enable_expr = f"between(t,{t_start:.2f},{t_end:.2f})"
            escaped_text = cue.search_query.replace("'", "").replace(":", r"\:")

            # Semi-transparent dark rounded badge + callout text
            card_filter = (
                f"drawbox=x=120:y=200:w=840:h=160:color=black@0.70:t=fill:enable='{enable_expr}',"
                f"drawtext=text='{escaped_text}':fontsize=44:fontcolor=white:"
                f"x=(w-text_w)/2:y=255:enable='{enable_expr}'"
            )
            filters.append(card_filter)

        return filters

    def build_filtergraph(
        self,
        layout: LayoutMode,
        zooms: list[PunchZoomInterval],
        broll_cues: list[BrollCue],
        ass_path: Path | str | None,
        clip_start_ms: int,
        clip_duration_sec: float,
    ) -> str:
        """Compile complete video filtergraph pipeline."""
        video_filters: list[str] = []

        # 1. Reframing & Zoom
        crop_chain = self.build_crop_filter(layout, zooms)
        video_filters.append(crop_chain)

        # 2. B-Roll & Text Card Overlays
        broll_filters = self.build_broll_overlay_filter(
            broll_cues, clip_start_ms, clip_duration_sec
        )
        if broll_filters:
            video_filters.extend(broll_filters)

        # 3. Subtitle Burn-in
        if ass_path:
            p = Path(ass_path)
            if p.is_file():
                escaped_ass = escape_ffmpeg_filter_path(p.resolve())
                video_filters.append(f"ass='{escaped_ass}'")

        return ",".join(video_filters)


def build_render_command(
    ffmpeg_bin: str,
    source_path: Path | str,
    output_path: Path | str,
    start_sec: float,
    duration_sec: float,
    filtergraph: str,
    audio_normalize: bool = True,
    micro_silence_trim: bool = False,
) -> list[str]:
    """Assemble safe FFmpeg command array with audio loudnorm and video filtergraph."""
    cmd = [
        ffmpeg_bin,
        "-y",
        "-ss",
        f"{start_sec:.3f}",
        "-t",
        f"{duration_sec:.3f}",
        "-i",
        str(source_path),
        "-vf",
        filtergraph,
    ]

    # Audio filter chain
    audio_filters: list[str] = []
    if micro_silence_trim:
        audio_filters.append("silenceremove=stop_periods=-1:stop_duration=0.6:stop_threshold=-40dB")
    if audio_normalize:
        audio_filters.append("loudnorm=I=-14:TP=-1.5:LRA=11")

    if audio_filters:
        cmd.extend(["-af", ",".join(audio_filters)])

    cmd.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    return cmd


def build_hook_remix_command(
    ffmpeg_bin: str,
    source_path: Path | str,
    output_path: Path | str,
    hook_start_sec: float,
    hook_duration_sec: float,
    body_start_sec: float,
    body_duration_sec: float,
    filtergraph_body: str,
    ass_path: Path | str | None = None,
) -> list[str]:
    """Assemble FFmpeg command rendering hook remix (quote + flash + full cut)."""
    # Escaped ass path
    ass_filter = ""
    if ass_path and Path(ass_path).is_file():
        escaped_ass = escape_ffmpeg_filter_path(Path(ass_path).resolve())
        ass_filter = f",ass='{escaped_ass}'"

    # Filtergraph concatenating [hook] -> [white_flash] -> [body]
    # Input 0: source video hook
    # Input 1: source video body
    fade_st = max(0.0, hook_duration_sec - 0.15)
    complex_filter = (
        f"[0:v]crop=w='min(iw,ih*9/16)':h='min(ih,iw*16/9)':x='(iw-ow)/2':y='(ih-oh)/2',"
        f"scale=1080:1920,fade=t=out:st={fade_st:.2f}:d=0.15:c=white[v_hook];"
        f"[1:v]{filtergraph_body}{ass_filter}[v_body];"
        f"[v_hook][0:a][v_body][1:a]concat=n=2:v=1:a=1[v_out][a_pre];"
        f"[a_pre]loudnorm=I=-14:TP=-1.5:LRA=11[a_out]"
    )

    cmd = [
        ffmpeg_bin,
        "-y",
        "-ss",
        f"{hook_start_sec:.3f}",
        "-t",
        f"{hook_duration_sec:.3f}",
        "-i",
        str(source_path),
        "-ss",
        f"{body_start_sec:.3f}",
        "-t",
        f"{body_duration_sec:.3f}",
        "-i",
        str(source_path),
        "-filter_complex",
        complex_filter,
        "-map",
        "[v_out]",
        "-map",
        "[a_out]",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    return cmd


def execute_ffmpeg_render(
    cmd: list[str],
    output_path: Path,
    timeout_sec: float = 300.0,
) -> bool:
    """Execute FFmpeg render command safely using atomic replacement."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_suffix(f".tmp-{os.getpid()}-{output_path.suffix}")

    # Point output to tmp_path in the command array
    exec_cmd = list(cmd)
    exec_cmd[-1] = str(tmp_path)

    try:
        proc = subprocess.run(
            exec_cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        if proc.returncode != 0:
            logger.error(
                "FFmpeg rendering failed (code %d): %s",
                proc.returncode,
                (proc.stderr or "")[-800:],
            )
            if tmp_path.exists():
                tmp_path.unlink()
            return False

        if not tmp_path.is_file() or tmp_path.stat().st_size == 0:
            logger.error("FFmpeg render created an empty output file: %s", tmp_path)
            if tmp_path.exists():
                tmp_path.unlink()
            return False

        # Atomic replacement
        tmp_path.replace(output_path)
        return True
    except subprocess.TimeoutExpired:
        logger.error("FFmpeg render timed out after %ds on %s", timeout_sec, output_path)
        if tmp_path.exists():
            tmp_path.unlink()
        return False
    except Exception as e:
        logger.error("Unexpected error during FFmpeg execution: %s", e)
        if tmp_path.exists():
            tmp_path.unlink()
        return False


def run_render_stage(
    manifest: QattaManifest,
    settings: QattaSettings | None = None,
    renders_dir: Path | None = None,
    execute_ffmpeg: bool = True,
) -> QattaManifest:
    """Execute Stage s07 rendering and compute monetization safety metadata."""
    settings = settings or QattaSettings()
    out_dir = renders_dir or settings.manifest_path(manifest.project_id).parent / "renders"
    out_dir.mkdir(parents=True, exist_ok=True)

    ffmpeg_bin = shutil.which("ffmpeg")
    if execute_ffmpeg and not ffmpeg_bin:
        logger.warning("ffmpeg binary not found on PATH. Commands will be prepared but skipped.")
        execute_ffmpeg = False

    camera_solver = CameraSolver(
        frame_width=manifest.video_width or 1920,
        frame_height=manifest.video_height or 1080,
    )
    graph_builder = FFmpegFilterGraphBuilder(target_width=1080, target_height=1920)

    for candidate in manifest.candidates:
        clip_id = candidate.clip_id
        start_sec = candidate.start_ms / 1000.0
        duration_sec = candidate.duration_sec

        # 1. Shot layout decomposition
        shots = camera_solver.solve_clip(
            clip_start_ms=candidate.start_ms,
            clip_end_ms=candidate.end_ms,
            scene_cuts_ms=manifest.scene_cuts_ms,
        )
        primary_layout = shots[0].layout if shots else LayoutMode.SINGLE_SPEAKER

        # 2. Detect punch-in zooms
        zooms = detect_punch_in_zooms(candidate, manifest.atomic_utterances)

        # 3. Calculate visual transformation ratio
        trans_ratio = compute_visual_transformation_ratio(
            candidate=candidate,
            shots=shots,
            zooms=zooms,
            broll_cues=candidate.broll_cues,
        )

        ypp_safe = trans_ratio >= 0.35
        if not ypp_safe:
            logger.warning(
                "Clip '%s' visual_transformation_ratio=%.2f < 0.35 threshold. "
                "At risk for YouTube Reused Content demonetization.",
                clip_id,
                trans_ratio,
            )

        candidate.evidence_log.append(
            f"s07_render: visual_transformation_ratio={trans_ratio:.3f} "
            f"(ypp_safe={ypp_safe}, zooms={len(zooms)}, brolls={len(candidate.broll_cues)})"
        )

        # 4. Populate MonetizationMeta
        pinned_cta = (
            candidate.draft_pinned_comment_cta
            or "شاركنا رأيك في التعليقات! لا تنسى الاشتراك للمزيد من المحتوى التقني."
        )
        titles = candidate.draft_curiosity_titles or [
            f"سر {clip_id} في 60 ثانية",
            f"كيف تستفيد من {clip_id}",
        ]
        candidate.monetization = MonetizationMeta(
            visual_transformation_ratio=trans_ratio,
            seamless_loop_score=0.85,
            pinned_comment_cta=pinned_cta,
            curiosity_titles=titles,
            ypp_safe=ypp_safe,
        )

        # 5. Build filtergraph
        ass_sub_path = candidate.rendered_paths.get("ass_captions")
        filtergraph = graph_builder.build_filtergraph(
            layout=primary_layout,
            zooms=zooms,
            broll_cues=candidate.broll_cues,
            ass_path=ass_sub_path,
            clip_start_ms=candidate.start_ms,
            clip_duration_sec=duration_sec,
        )

        # 6. Render original cut
        orig_out = out_dir / f"{clip_id}_original.mp4"
        orig_cmd = build_render_command(
            ffmpeg_bin=ffmpeg_bin or "ffmpeg",
            source_path=manifest.source_path,
            output_path=orig_out,
            start_sec=start_sec,
            duration_sec=duration_sec,
            filtergraph=filtergraph,
            audio_normalize=True,
        )

        if execute_ffmpeg and ffmpeg_bin:
            success = execute_ffmpeg_render(
                orig_cmd, orig_out, timeout_sec=settings.ffmpeg_timeout_seconds
            )
            if success:
                candidate.rendered_paths["vertical_9_16"] = str(orig_out.resolve())
                candidate.rendered_paths["original"] = str(orig_out.resolve())
        else:
            candidate.rendered_paths["vertical_9_16"] = str(orig_out.resolve())

        # 7. Render hook remix cut if enabled
        if candidate.hook_remix.enabled and candidate.hook_remix.source_start_ms is not None:
            remix_out = out_dir / f"{clip_id}_hook_remix.mp4"
            h_start = candidate.hook_remix.source_start_ms / 1000.0
            default_end = candidate.hook_remix.source_start_ms + 2500
            end_ms = candidate.hook_remix.source_end_ms or default_end
            h_dur = min(3.0, max(1.5, (end_ms / 1000.0) - h_start))

            remix_cmd = build_hook_remix_command(
                ffmpeg_bin=ffmpeg_bin or "ffmpeg",
                source_path=manifest.source_path,
                output_path=remix_out,
                hook_start_sec=h_start,
                hook_duration_sec=h_dur,
                body_start_sec=start_sec,
                body_duration_sec=duration_sec,
                filtergraph_body=filtergraph,
                ass_path=ass_sub_path,
            )

            if execute_ffmpeg and ffmpeg_bin:
                success_remix = execute_ffmpeg_render(
                    remix_cmd, remix_out, timeout_sec=settings.ffmpeg_timeout_seconds
                )
                if success_remix:
                    candidate.rendered_paths["vertical_9_16_hook_remix"] = str(remix_out.resolve())
            else:
                candidate.rendered_paths["vertical_9_16_hook_remix"] = str(remix_out.resolve())

    return manifest
