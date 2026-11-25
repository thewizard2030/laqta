"""Local face detection for the reframe stage.

Only OpenCV's bundled Haar cascade is used. It ships inside the
``opencv-python`` wheel that ``scenedetect`` already requires, so enabling
face-guided framing downloads nothing, adds no dependency, and sends nothing
off the machine.

Honesty limits — these are properties of the chosen detector, not bugs to
"fix" later without a new decision:

- **Frontal faces only.** Haar's default cascade is trained on frontal
  upright faces. Profile faces, heavy occlusion, backlight and low light are
  missed. A missed frame is not an error: the solver already tolerates gaps.
- **No mouth geometry.** A Haar box has no landmarks, so ``mar`` stays 0.0 and
  ``is_speaking`` stays False. Laqta does not claim to detect who is talking.
- **No identity.** ``face_id`` is an index within a single frame, not a
  tracked person across frames. There is no speaker identification anywhere
  in this package, and none may be inferred from these values.
- **No confidence score.** ``cv2.CascadeClassifier`` returns boxes only, so
  ``BoundingBox.confidence`` is 1.0 for a detection and nothing exists for a
  miss. Treat it as "a box was returned", not as a calibrated probability.

Frames are downscaled before detection (``downscale_width``, default 320) as
a CPU trade-off: Haar cost grows with area, and a talking-head face is large
in frame. The cost is that a genuinely small face in a wide shot is missed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from qatta.stages.s06_reframe_subs.camera_solver import (
    BoundingBox,
    FaceDetection,
    FrameObservation,
)
from qatta.stages.s06_reframe_subs.frame_sampler import SampledFrame

logger = logging.getLogger("qatta.s06_reframe.detector")

# The cascade file that ships inside every `opencv-python` wheel.
CASCADE_FILENAME = "haarcascade_frontalface_default.xml"

# `scaleFactor` / `minNeighbors` are OpenCV's documented starting point for
# frontal-face detection: a 10% pyramid step keeps small faces reachable while
# 5 neighbours suppresses the false positives that a step of 1.05 produces.
DEFAULT_SCALE_FACTOR = 1.1
DEFAULT_MIN_NEIGHBORS = 5
DEFAULT_DOWNSCALE_WIDTH = 320
DEFAULT_MAX_FACES = 4
# A box smaller than this fraction of the frame's short side is noise at these
# resolutions; 24 px is the smallest window Haar reliably classifies.
DEFAULT_MIN_FACE_RATIO = 0.05
DEFAULT_MIN_FACE_PX = 24

_INSTALL_HINT = (
    "OpenCV (cv2) is not installed. Install the analysis extra: "
    "pip install --require-hashes -r backend/requirements-analysis-lock.txt"
)


class DetectorUnavailableError(RuntimeError):
    """Raised when a detector cannot run, with a reason a user can act on."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@runtime_checkable
class FaceDetector(Protocol):
    """A detector turns one BGR frame into one :class:`FrameObservation`."""

    name: str

    def detect(self, frame_bgr: Any, timestamp_ms: int) -> FrameObservation:
        """Return the faces visible in ``frame_bgr`` at ``timestamp_ms``.

        Must never raise for a frame it simply cannot analyse; return an
        observation with no faces instead. Raising is reserved for "this
        detector cannot run at all" (:class:`DetectorUnavailableError`).
        """
        ...


def detector_status() -> tuple[bool, str | None]:
    """Report whether the OpenCV Haar detector can run, with the reason if not.

    Never raises: the stage calls this to decide between detecting and
    recording an explicit skip reason.
    """
    try:
        import cv2
    except ImportError:
        return False, _INSTALL_HINT

    try:
        cascade_dir = Path(cv2.data.haarcascades)
    except (AttributeError, TypeError):
        return False, "This cv2 build does not expose cv2.data.haarcascades."
    cascade_path = cascade_dir / CASCADE_FILENAME
    if not cascade_path.is_file():
        return False, f"OpenCV's bundled Haar cascade is missing at {cascade_path}."
    return True, None


class NullDetector:
    """A detector that reports no faces.

    Used when face-guided framing is disabled, so the stage has a real object
    to call instead of a special case in the middle of the loop.
    """

    name = "none"

    def detect(self, frame_bgr: Any, timestamp_ms: int) -> FrameObservation:
        return FrameObservation(timestamp_ms=timestamp_ms, faces=[])


class OpenCVHaarDetector:
    """Frontal-face detection with OpenCV's bundled Haar cascade."""

    name = "opencv_haar"

    def __init__(
        self,
        *,
        downscale_width: int = DEFAULT_DOWNSCALE_WIDTH,
        max_faces: int = DEFAULT_MAX_FACES,
        min_face_ratio: float = DEFAULT_MIN_FACE_RATIO,
        min_face_px: int = DEFAULT_MIN_FACE_PX,
    ):
        if downscale_width < 32:
            raise ValueError("downscale_width must be at least 32 pixels.")
        if max_faces < 1:
            raise ValueError("max_faces must be at least 1.")
        if not 0.0 < min_face_ratio < 1.0:
            raise ValueError("min_face_ratio must be between 0 and 1.")
        if min_face_px < 8:
            raise ValueError("min_face_px must be at least 8 pixels.")

        self.downscale_width = downscale_width
        self.max_faces = max_faces
        self.min_face_ratio = min_face_ratio
        self.min_face_px = min_face_px

        self._cv2: Any = None
        self._cascade: Any = None
        self._load()

    def _load(self) -> None:
        """Import cv2 and load the cascade once, with an actionable error."""
        try:
            import cv2
        except ImportError as exc:
            raise DetectorUnavailableError(_INSTALL_HINT) from exc

        try:
            cascade_path = Path(cv2.data.haarcascades) / CASCADE_FILENAME
        except (AttributeError, TypeError) as exc:
            raise DetectorUnavailableError(
                "This cv2 build does not expose cv2.data.haarcascades."
            ) from exc

        if not cascade_path.is_file():
            raise DetectorUnavailableError(
                f"OpenCV's bundled Haar cascade is missing at {cascade_path}."
            )

        cascade = cv2.CascadeClassifier(str(cascade_path))
        # CascadeClassifier reports failure by returning an empty object; the
        # empty() check is the only reliable signal across cv2 versions.
        if cascade is None or (hasattr(cascade, "empty") and cascade.empty()):
            raise DetectorUnavailableError(
                f"OpenCV could not load the Haar cascade at {cascade_path}."
            )

        self._cv2 = cv2
        self._cascade = cascade

    def detect(self, frame_bgr: Any, timestamp_ms: int) -> FrameObservation:
        """Detect frontal faces, returning normalized boxes.

        A frame that cannot be analysed (empty, wrong shape, unexpected dtype)
        yields an observation with no faces rather than an exception: one bad
        frame must not abort a whole clip.
        """
        cv2 = self._cv2
        if frame_bgr is None or getattr(frame_bgr, "shape", None) is None:
            return FrameObservation(timestamp_ms=timestamp_ms, faces=[])

        shape = frame_bgr.shape
        if len(shape) < 2:
            return FrameObservation(timestamp_ms=timestamp_ms, faces=[])
        height, width = int(shape[0]), int(shape[1])
        if height <= 0 or width <= 0:
            return FrameObservation(timestamp_ms=timestamp_ms, faces=[])

        scale = min(1.0, self.downscale_width / float(width))
        if scale < 1.0:
            small = cv2.resize(
                frame_bgr,
                (max(1, int(width * scale)), max(1, int(height * scale))),
                interpolation=cv2.INTER_AREA,
            )
        else:
            small = frame_bgr

        small_h, small_w = int(small.shape[0]), int(small.shape[1])
        if small_h <= 0 or small_w <= 0:
            return FrameObservation(timestamp_ms=timestamp_ms, faces=[])

        try:
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            gray = cv2.equalizeHist(gray)
        except Exception:  # cv2 raises cv2.error for odd dtypes/shapes
            return FrameObservation(timestamp_ms=timestamp_ms, faces=[])

        min_px = max(self.min_face_px, int(round(min(small_w, small_h) * self.min_face_ratio)))
        try:
            boxes = self._cascade.detectMultiScale(
                gray,
                scaleFactor=DEFAULT_SCALE_FACTOR,
                minNeighbors=DEFAULT_MIN_NEIGHBORS,
                minSize=(min_px, min_px),
            )
        except Exception:  # cv2.error on an unexpected dtype/shape
            # One unanalysable frame must not abort a whole clip; the solver
            # already tolerates gaps in the observation series.
            logger.debug("Haar detection failed for one frame; treating it as empty.")
            return FrameObservation(timestamp_ms=timestamp_ms, faces=[])

        detections: list[FaceDetection] = []
        for raw in boxes:
            # Haar returns (x, y, w, h) in pixels of the downscaled frame.
            x, y, box_w, box_h = (float(v) for v in raw[:4])
            if box_w <= 0 or box_h <= 0:
                continue
            detections.append(
                FaceDetection(
                    bbox=BoundingBox(
                        x_min=_clamp01(x / small_w),
                        y_min=_clamp01(y / small_h),
                        x_max=_clamp01((x + box_w) / small_w),
                        y_max=_clamp01((y + box_h) / small_h),
                        # Haar returns no score; presence of a box is the
                        # only signal. Never present this as calibrated.
                        confidence=1.0,
                    ),
                    # No landmarks exist, so no mouth geometry and no
                    # speaking claim. These stay false/zero by construction.
                    mar=0.0,
                    is_speaking=False,
                    face_id=0,
                )
            )

        # Largest face first: the solver's deadband logic cares about the
        # dominant face, and the cap should keep the big ones.
        detections.sort(key=lambda d: d.bbox.area, reverse=True)
        detections = detections[: self.max_faces]
        for index, detection in enumerate(detections):
            detection.face_id = index

        return FrameObservation(timestamp_ms=timestamp_ms, faces=detections)


def _clamp01(value: float) -> float:
    """Keep a normalized coordinate inside [0, 1]."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _imread(path: Path) -> Any | None:
    """Read one JPEG with OpenCV, or return None when it cannot be decoded."""
    import cv2

    return cv2.imread(str(path))


def observe_frames(
    detector: FaceDetector,
    frames: Iterable[SampledFrame],
    *,
    reader: Callable[[Path], Any | None] | None = None,
) -> list[FrameObservation]:
    """Turn sampled frames into one observation per readable frame.

    Decoding lives here, next to the only other place that knows about cv2, so
    the stage never imports OpenCV directly. ``reader`` is injectable for the
    same reason ``detect`` is tested with a fake cv2: the logic must be
    exercisable on a machine without the analysis extra.

    A frame that will not decode is skipped rather than aborting the clip. The
    returned list is therefore shorter than the input when frames are
    unreadable, which the caller reports as ``frames_analysed`` — it must not
    assume the two counts match.
    """
    read = reader or _imread
    observations: list[FrameObservation] = []
    for frame in frames:
        image = read(frame.path)
        if image is None:
            logger.debug("Skipping a sampled frame that would not decode: %s", frame.path)
            continue
        observations.append(detector.detect(image, frame.timestamp_ms))
    return observations


def build_detector(name: str = "opencv_haar") -> FaceDetector:
    """Construct the named detector, raising ``DetectorUnavailableError`` if it cannot run."""
    if name == "none":
        return NullDetector()
    if name == "opencv_haar":
        return OpenCVHaarDetector()
    raise DetectorUnavailableError(f"Unknown face detector '{name}'. Available: opencv_haar, none.")
