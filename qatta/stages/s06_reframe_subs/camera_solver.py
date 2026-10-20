"""Stage s06_reframe_subs — Permissive CV Camera Solver & 9:16 Reframe Engine.

Features:
- Fast 5 FPS sampling on winning clips only (low CPU overhead).
- Face detection (MediaPipe / OpenCV YuNet fallback / Deterministic fallback).
- FaceMesh Mouth Aspect Ratio (MAR) speech detection.
- Scene cut segmentation using Stage 03 cuts.
- Scene-Aware Hysteresis Deadband Solver:
  * Inside a shot: 0% pan locked unless speaker exits middle 15% deadband.
  * When moving: smooth trajectory via cubic bezier / smoothstep filter.
  * Across scene cuts: instant snap (zero whip-pan, filter history reset).
- Layout State Machine per shot:
  * SINGLE_SPEAKER: Full 9:16 vertical crop (1080x1920).
  * DUAL_SPLIT: Top/Bottom split-screen when 2 active faces alternate speaking <= 4s.
  * SCREENSHARE_PIP: >75% static slide/code + small corner face -> 60% top / 40% bottom.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

logger = logging.getLogger("qatta.s06_reframe")


class LayoutMode(StrEnum):
    """Layout composition mode for a shot."""

    SINGLE_SPEAKER = "SINGLE_SPEAKER"
    DUAL_SPLIT = "DUAL_SPLIT"
    SCREENSHARE_PIP = "SCREENSHARE_PIP"


@dataclass
class BoundingBox:
    """Normalized bounding box [0.0, 1.0]."""

    x_min: float
    y_min: float
    x_max: float
    y_max: float
    confidence: float = 1.0

    @property
    def center_x(self) -> float:
        return (self.x_min + self.x_max) / 2.0

    @property
    def center_y(self) -> float:
        return (self.y_min + self.y_max) / 2.0

    @property
    def width(self) -> float:
        return max(0.0, self.x_max - self.x_min)

    @property
    def height(self) -> float:
        return max(0.0, self.y_max - self.y_min)

    @property
    def area(self) -> float:
        return self.width * self.height


@dataclass
class FaceDetection:
    """Detected face with bounding box, MAR, and active speaking status."""

    bbox: BoundingBox
    mar: float = 0.0  # Mouth Aspect Ratio
    is_speaking: bool = False
    face_id: int = 0


@dataclass
class FrameObservation:
    """Observation at a specific timestamp sampled at 5 FPS."""

    timestamp_ms: int
    faces: list[FaceDetection] = field(default_factory=list)
    is_screen_share: bool = False
    static_content_ratio: float = 0.0


@dataclass
class ShotSegment:
    """A continuous video shot bounded by scene cuts."""

    shot_index: int
    start_ms: int
    end_ms: int
    layout: LayoutMode = LayoutMode.SINGLE_SPEAKER
    observations: list[FrameObservation] = field(default_factory=list)
    crop_trajectory: list[tuple[int, float]] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


def compute_mouth_aspect_ratio(
    upper_lip_y: float,
    lower_lip_y: float,
    left_corner_x: float,
    right_corner_x: float,
) -> float:
    """Calculate normalized Mouth Aspect Ratio (MAR).

    MAR = |lower_lip - upper_lip| / |right_corner - left_corner|
    """
    lip_dist = abs(lower_lip_y - upper_lip_y)
    mouth_width = abs(right_corner_x - left_corner_x)
    if mouth_width < 1e-5:
        return 0.0
    return lip_dist / mouth_width


def partition_clip_into_shots(
    clip_start_ms: int,
    clip_end_ms: int,
    scene_cuts_ms: list[int],
) -> list[tuple[int, int]]:
    """Partition [clip_start_ms, clip_end_ms] into shot intervals using scene cuts."""
    valid_cuts = sorted(cut for cut in scene_cuts_ms if clip_start_ms < cut < clip_end_ms)
    boundaries = [clip_start_ms, *valid_cuts, clip_end_ms]
    shots = []
    for i in range(len(boundaries) - 1):
        s_start = boundaries[i]
        s_end = boundaries[i + 1]
        if s_end > s_start:
            shots.append((s_start, s_end))
    return shots


class SceneAwareHysteresisSolver:
    """Scene-Aware Hysteresis Deadband Camera Solver for 9:16 vertical reframing.

    Enforces two invariant rules:
    1. Deadband Lock: Within a single shot, keep the crop window completely
       locked (0% pan) unless the active speaker's face center exits the middle
       15% deadband zone.
    2. Scene-Cut Snap: Across a scene cut boundary, immediately reset filter
       history and snap the camera center to the new shot's speaker, preventing
       whip-pans across distinct camera angles.
    """

    def __init__(
        self,
        frame_width: int = 1920,
        frame_height: int = 1080,
        target_aspect_ratio: float = 9 / 16,
        deadband_ratio: float = 0.15,
        smoothing_factor: float = 0.25,
    ):
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.target_aspect_ratio = target_aspect_ratio
        self.deadband_ratio = deadband_ratio
        self.smoothing_factor = smoothing_factor

        # Normalized width of 9:16 crop window in a frame_width x frame_height canvas
        crop_w_px = frame_height * target_aspect_ratio
        self.w_crop = crop_w_px / frame_width
        self.min_center = self.w_crop / 2.0
        self.max_center = 1.0 - (self.w_crop / 2.0)

        # Middle 15% deadband half-width
        self.deadband_half = (self.w_crop * self.deadband_ratio) / 2.0

        self.current_center: float | None = None
        self.last_timestamp_ms: int | None = None
        self.history: list[tuple[int, float]] = []

    def reset(self, initial_center: float | None = None) -> None:
        """Reset the solver's smoothing history."""
        self.history.clear()
        if initial_center is not None:
            self.current_center = min(max(initial_center, self.min_center), self.max_center)
        else:
            self.current_center = None
        self.last_timestamp_ms = None

    def on_scene_cut(self, timestamp_ms: int, target_x: float) -> float:
        """Instant snap on scene cut: reset filter and snap directly to target."""
        clamped = min(max(target_x, self.min_center), self.max_center)
        self.reset(clamped)
        self.last_timestamp_ms = timestamp_ms
        self.history.append((timestamp_ms, clamped))
        return clamped

    def update(
        self,
        timestamp_ms: int,
        target_x: float,
        is_scene_cut: bool = False,
    ) -> float:
        """Update the camera position for a single frame.

        If is_scene_cut is True, executes an immediate snap with zero smoothing.
        Otherwise, holds steady if target_x is inside the deadband, or applies
        cubic smoothstep easing toward target if target_x is outside.
        """
        if is_scene_cut or self.current_center is None:
            return self.on_scene_cut(timestamp_ms, target_x)

        target_clamped = min(max(target_x, self.min_center), self.max_center)
        dist = abs(target_clamped - self.current_center)

        # 1. Hysteresis Deadband check: hold 100% steady (0% pan) if inside deadband
        if dist <= self.deadband_half:
            self.history.append((timestamp_ms, self.current_center))
            self.last_timestamp_ms = timestamp_ms
            return self.current_center

        # 2. Outside deadband: smooth transition using cubic smoothstep
        # Compute progress parameter scaled by smoothing factor
        t = min(1.0, max(0.0, self.smoothing_factor))
        # Cubic smoothstep easing: 3t^2 - 2t^3
        s = t * t * (3.0 - 2.0 * t)
        new_center = self.current_center + s * (target_clamped - self.current_center)
        new_center = min(max(new_center, self.min_center), self.max_center)

        self.current_center = new_center
        self.last_timestamp_ms = timestamp_ms
        self.history.append((timestamp_ms, new_center))
        return new_center

    def solve_trajectory(
        self,
        observations: list[tuple[int, float]],
        scene_cuts_ms: list[int],
    ) -> list[tuple[int, float]]:
        """Compute complete camera center trajectory across observations."""
        if not observations:
            return []

        cuts_set = set(scene_cuts_ms)
        trajectory: list[tuple[int, float]] = []

        self.reset()
        for idx, (ts_ms, target_x) in enumerate(observations):
            is_cut = (idx == 0) or (ts_ms in cuts_set)
            center = self.update(ts_ms, target_x, is_scene_cut=is_cut)
            trajectory.append((ts_ms, center))

        return trajectory


class LayoutStateMachine:
    """Evaluates frame observations within a shot to determine optimal layout."""

    @classmethod
    def classify_shot(
        cls,
        observations: list[FrameObservation],
        alternate_speaking_window_ms: int = 4000,
    ) -> LayoutMode:
        """Classify a shot into SINGLE_SPEAKER, DUAL_SPLIT, or SCREENSHARE_PIP."""
        if not observations:
            return LayoutMode.SINGLE_SPEAKER

        # 1. Check for SCREENSHARE_PIP:
        # >75% of the frame is static slide/code content with a small corner face
        screen_share_frames = sum(
            1
            for obs in observations
            if obs.is_screen_share
            or (obs.static_content_ratio > 0.75 and any(f.bbox.area < 0.15 for f in obs.faces))
        )
        if screen_share_frames / len(observations) >= 0.5:
            return LayoutMode.SCREENSHARE_PIP

        # 2. Check for DUAL_SPLIT:
        # 2 active faces alternate speaking within 4 seconds (4000 ms)
        speaking_events: list[tuple[int, int]] = []  # (timestamp_ms, face_id)
        for obs in observations:
            for face in obs.faces:
                if face.is_speaking:
                    speaking_events.append((obs.timestamp_ms, face.face_id))

        if len(speaking_events) >= 2:
            # Check if at least two distinct face_ids spoke within alternate_speaking_window_ms
            distinct_faces = {face_id for _, face_id in speaking_events}
            if len(distinct_faces) >= 2:
                # Verify alternation timing
                for i in range(len(speaking_events) - 1):
                    t1, f1 = speaking_events[i]
                    for j in range(i + 1, len(speaking_events)):
                        t2, f2 = speaking_events[j]
                        if f1 != f2 and abs(t2 - t1) <= alternate_speaking_window_ms:
                            return LayoutMode.DUAL_SPLIT

        # 3. Default to SINGLE_SPEAKER vertical reframing
        return LayoutMode.SINGLE_SPEAKER


class CameraSolver:
    """End-to-end camera solver coordinating detection, layout, and trajectories."""

    def __init__(
        self,
        frame_width: int = 1920,
        frame_height: int = 1080,
        detector: Callable[[int], FrameObservation] | None = None,
    ):
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.detector = detector
        self.hysteresis_solver = SceneAwareHysteresisSolver(
            frame_width=frame_width,
            frame_height=frame_height,
        )

    def sample_timestamps(
        self,
        start_ms: int,
        end_ms: int,
        fps: float = 5.0,
    ) -> list[int]:
        """Generate 5 FPS sample timestamps for winning clip."""
        interval_ms = int(round(1000.0 / fps))
        ts = start_ms
        timestamps = []
        while ts <= end_ms:
            timestamps.append(ts)
            ts += interval_ms
        return timestamps

    def solve_clip(
        self,
        clip_start_ms: int,
        clip_end_ms: int,
        scene_cuts_ms: list[int],
        observations: list[FrameObservation] | None = None,
    ) -> list[ShotSegment]:
        """Solve layout and crop trajectories for all shots in a clip."""
        shot_spans = partition_clip_into_shots(clip_start_ms, clip_end_ms, scene_cuts_ms)

        obs_by_ts: dict[int, FrameObservation] = {}
        if observations:
            obs_by_ts = {obs.timestamp_ms: obs for obs in observations}

        shot_segments: list[ShotSegment] = []

        for idx, (s_start, s_end) in enumerate(shot_spans):
            shot_obs = [obs for ts, obs in obs_by_ts.items() if s_start <= ts <= s_end]
            shot_obs.sort(key=lambda o: o.timestamp_ms)

            # Classify layout
            layout = LayoutStateMachine.classify_shot(shot_obs)

            # Build trajectory for this shot
            targets: list[tuple[int, float]] = []
            for obs in shot_obs:
                speaker_x = 0.5  # default frame center
                speaking_faces = [f for f in obs.faces if f.is_speaking]
                if speaking_faces:
                    speaker_x = speaking_faces[0].bbox.center_x
                elif obs.faces:
                    speaker_x = obs.faces[0].bbox.center_x
                targets.append((obs.timestamp_ms, speaker_x))

            # Snap at the beginning of each shot (zero whip-pan!)
            shot_trajectory = []
            for t_idx, (ts, tx) in enumerate(targets):
                is_cut = t_idx == 0
                center = self.hysteresis_solver.update(ts, tx, is_scene_cut=is_cut)
                shot_trajectory.append((ts, center))

            segment = ShotSegment(
                shot_index=idx,
                start_ms=s_start,
                end_ms=s_end,
                layout=layout,
                observations=shot_obs,
                crop_trajectory=shot_trajectory,
            )
            shot_segments.append(segment)

        return shot_segments
