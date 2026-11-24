"""Tests for the reframe stage's face detector and bounded frame sampler.

`cv2` and `ffmpeg` are the boundaries: the unit tests replace them with fakes
so the logic is exercised on every machine, and a handful of gated tests run
the real tools when they happen to be installed. A test that needs the
analysis extra skips with a stated reason instead of passing vacuously.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

from qatta.stages.s06_reframe_subs import frame_sampler
from qatta.stages.s06_reframe_subs.detector import (
    CASCADE_FILENAME,
    DetectorUnavailableError,
    NullDetector,
    OpenCVHaarDetector,
    build_detector,
    detector_status,
)
from qatta.stages.s06_reframe_subs.frame_sampler import (
    DEFAULT_MAX_FRAMES,
    SAMPLE_WIDTH,
    FrameSamplingError,
    SampledFrame,
    SamplingCancelledError,
    build_sample_command,
    sample_frames,
    temporary_sample_dir,
)

FFMPEG = shutil.which("ffmpeg")


# ---------------------------------------------------------------------------
# A fake cv2: enough surface for the adapter, nothing more
# ---------------------------------------------------------------------------


class FakeArray:
    """Stands in for a numpy ndarray: the adapter only reads ``.shape``."""

    def __init__(self, shape: tuple[int, ...]):
        self.shape = shape


class FakeCascade:
    def __init__(self, boxes: list[tuple[int, int, int, int]] | None = None):
        self.boxes = boxes or []
        self.calls: list[dict] = []

    def empty(self) -> bool:
        return False

    def detectMultiScale(self, gray, **kwargs):  # noqa: N802 - cv2's own name
        self.calls.append({"shape": gray.shape, **kwargs})
        return self.boxes


def install_fake_cv2(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    boxes: list[tuple[int, int, int, int]] | None = None,
    write_cascade: bool = True,
) -> tuple[types.ModuleType, FakeCascade]:
    """Install a fake ``cv2`` module and return it with its cascade object."""
    cascade_dir = tmp_path / "haarcascades"
    cascade_dir.mkdir(exist_ok=True)
    if write_cascade:
        (cascade_dir / CASCADE_FILENAME).write_bytes(b"fake cascade")

    cascade = FakeCascade(boxes)

    module = types.ModuleType("cv2")
    module.data = types.SimpleNamespace(haarcascades=str(cascade_dir))
    module.CascadeClassifier = lambda _path: cascade
    module.INTER_AREA = 3
    module.COLOR_BGR2GRAY = 6

    def _resize(frame, size, interpolation=None):
        width, height = size
        return FakeArray((height, width, 3))

    def _cvt_color(frame, code):
        return FakeArray(frame.shape)

    def _equalize_hist(frame):
        return FakeArray(frame.shape)

    module.resize = _resize
    module.cvtColor = _cvt_color
    module.equalizeHist = _equalize_hist

    monkeypatch.setitem(sys.modules, "cv2", module)
    return module, cascade


# ---------------------------------------------------------------------------
# Detector status: the stage's decision point
# ---------------------------------------------------------------------------


def test_detector_status_explains_a_missing_opencv(monkeypatch: pytest.MonkeyPatch) -> None:
    # A None entry in sys.modules makes `import cv2` raise ImportError.
    monkeypatch.setitem(sys.modules, "cv2", None)

    available, reason = detector_status()

    assert available is False
    assert reason is not None
    assert "analysis" in reason
    assert "requirements-analysis-lock.txt" in reason


def test_detector_status_reports_a_missing_cascade(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    install_fake_cv2(monkeypatch, tmp_path, write_cascade=False)

    available, reason = detector_status()

    assert available is False
    assert reason is not None
    assert "cascade is missing" in reason


def test_detector_status_is_available_when_cv2_and_cascade_exist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    install_fake_cv2(monkeypatch, tmp_path)

    assert detector_status() == (True, None)


def test_building_the_detector_without_cv2_raises_with_the_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "cv2", None)

    with pytest.raises(DetectorUnavailableError) as excinfo:
        OpenCVHaarDetector()

    assert "analysis" in excinfo.value.reason


# ---------------------------------------------------------------------------
# Detector behaviour
# ---------------------------------------------------------------------------


def test_boxes_are_normalized_sorted_by_area_and_numbered(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 640x360 frame: a 64x64 face is smaller than a 128x128 one.
    install_fake_cv2(monkeypatch, tmp_path, boxes=[(10, 10, 64, 64), (200, 40, 128, 128)])
    detector = OpenCVHaarDetector()

    observation = detector.detect(FakeArray((360, 640, 3)), timestamp_ms=1500)

    assert observation.timestamp_ms == 1500
    assert len(observation.faces) == 2
    # Largest first, so the cap keeps the dominant face.
    big, small = observation.faces
    assert big.bbox.area > small.bbox.area
    assert [face.face_id for face in observation.faces] == [0, 1]
    # Normalized against the downscaled frame (320x180), not the source.
    assert 0.0 <= big.bbox.x_min <= big.bbox.x_max <= 1.0
    assert 0.0 <= big.bbox.y_min <= big.bbox.y_max <= 1.0


def test_the_detector_never_claims_a_speaker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Haar has no landmarks, so no MAR and no speaking claim may appear."""
    install_fake_cv2(monkeypatch, tmp_path, boxes=[(10, 10, 64, 64)])
    detector = OpenCVHaarDetector()

    observation = detector.detect(FakeArray((360, 640, 3)), timestamp_ms=0)

    assert observation.faces
    for face in observation.faces:
        assert face.mar == 0.0
        assert face.is_speaking is False


def test_the_face_cap_keeps_the_largest_faces(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    install_fake_cv2(
        monkeypatch,
        tmp_path,
        boxes=[(0, 0, 20, 20), (100, 0, 100, 100), (200, 0, 50, 50)],
    )
    detector = OpenCVHaarDetector(max_faces=2)

    observation = detector.detect(FakeArray((360, 640, 3)), timestamp_ms=0)

    assert len(observation.faces) == 2
    assert [face.face_id for face in observation.faces] == [0, 1]
    assert observation.faces[0].bbox.width > observation.faces[1].bbox.width


def test_frames_are_downscaled_before_detection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, cascade = install_fake_cv2(monkeypatch, tmp_path)
    detector = OpenCVHaarDetector(downscale_width=SAMPLE_WIDTH)

    detector.detect(FakeArray((1080, 1920, 3)), timestamp_ms=0)

    assert cascade.calls
    gray_shape = cascade.calls[0]["shape"]
    assert gray_shape[1] <= SAMPLE_WIDTH
    # minSize is a real window, not a single pixel.
    assert cascade.calls[0]["minSize"][0] >= 24


def test_out_of_frame_boxes_are_clamped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # A box that runs past the frame edge must not produce coordinates > 1.
    install_fake_cv2(monkeypatch, tmp_path, boxes=[(300, 170, 400, 400)])
    detector = OpenCVHaarDetector()

    observation = detector.detect(FakeArray((360, 640, 3)), timestamp_ms=0)

    face = observation.faces[0]
    assert face.bbox.x_max == 1.0
    assert face.bbox.y_max == 1.0


@pytest.mark.parametrize(
    "frame",
    [None, FakeArray((0, 0, 3)), FakeArray((5,))],
    ids=["none", "empty", "one-dimensional"],
)
def test_an_unusable_frame_yields_no_faces_instead_of_raising(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, frame: object
) -> None:
    install_fake_cv2(monkeypatch, tmp_path)
    detector = OpenCVHaarDetector()

    observation = detector.detect(frame, timestamp_ms=42)

    assert observation.timestamp_ms == 42
    assert observation.faces == []


def test_a_detector_failure_on_one_frame_yields_no_faces(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """One unanalysable frame must not abort the clip."""
    _, cascade = install_fake_cv2(monkeypatch, tmp_path)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("cv2.error: unsupported depth")

    cascade.detectMultiScale = _boom  # type: ignore[method-assign]
    detector = OpenCVHaarDetector()

    observation = detector.detect(FakeArray((360, 640, 3)), timestamp_ms=99)

    assert observation.timestamp_ms == 99
    assert observation.faces == []


def test_the_null_detector_reports_nothing() -> None:
    observation = NullDetector().detect(FakeArray((10, 10, 3)), timestamp_ms=7)

    assert observation.timestamp_ms == 7
    assert observation.faces == []
    assert NullDetector.name == "none"


def test_build_detector_rejects_an_unknown_name() -> None:
    with pytest.raises(DetectorUnavailableError) as excinfo:
        build_detector("mediapipe_facemesh")

    assert "opencv_haar" in excinfo.value.reason


def test_build_detector_returns_the_null_detector_for_none() -> None:
    assert isinstance(build_detector("none"), NullDetector)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"downscale_width": 8}, "downscale_width"),
        ({"max_faces": 0}, "max_faces"),
        ({"min_face_ratio": 0.0}, "min_face_ratio"),
        ({"min_face_ratio": 1.0}, "min_face_ratio"),
        ({"min_face_px": 4}, "min_face_px"),
    ],
)
def test_detector_rejects_impossible_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    kwargs: dict,
    message: str,
) -> None:
    install_fake_cv2(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match=message):
        OpenCVHaarDetector(**kwargs)


# ---------------------------------------------------------------------------
# Sampler: the argv is the contract
# ---------------------------------------------------------------------------


def test_the_sample_command_is_a_plain_argument_array(tmp_path: Path) -> None:
    cmd = build_sample_command(
        ffmpeg_bin="/usr/bin/ffmpeg",
        input_path=Path("/media/clip with spaces.mp4"),
        out_dir=tmp_path,
        start_ms=1500,
        end_ms=4500,
        fps=5.0,
        max_frames=60,
    )

    assert cmd[0] == "/usr/bin/ffmpeg"
    assert cmd[cmd.index("-ss") + 1] == "1.500"
    assert cmd[cmd.index("-i") + 1] == "/media/clip with spaces.mp4"
    assert cmd[cmd.index("-t") + 1] == "3.000"
    assert cmd[cmd.index("-vf") + 1] == f"fps=5,scale={SAMPLE_WIDTH}:-2"
    assert cmd[cmd.index("-frames:v") + 1] == "60"
    assert cmd[-1] == str(tmp_path / frame_sampler.FRAME_PATTERN)
    # Never a shell string: the path stays one argv element, unquoted.
    assert "sh -c" not in " ".join(cmd)
    assert "-nostdin" in cmd


@pytest.mark.parametrize(
    ("start_ms", "end_ms", "fps", "max_frames", "message"),
    [
        (-1, 1000, 5.0, 10, "start_ms"),
        (1000, 1000, 5.0, 10, "greater than start_ms"),
        (2000, 1000, 5.0, 10, "greater than start_ms"),
        (0, 1000, 0.0, 10, "fps"),
        (0, 1000, 31.0, 10, "fps"),
        (0, 1000, 5.0, 0, "max_frames"),
    ],
)
def test_the_sample_command_rejects_impossible_spans(
    tmp_path: Path,
    start_ms: int,
    end_ms: int,
    fps: float,
    max_frames: int,
    message: str,
) -> None:
    with pytest.raises(FrameSamplingError, match=message):
        build_sample_command(
            ffmpeg_bin="ffmpeg",
            input_path=tmp_path / "in.mp4",
            out_dir=tmp_path,
            start_ms=start_ms,
            end_ms=end_ms,
            fps=fps,
            max_frames=max_frames,
        )


# ---------------------------------------------------------------------------
# Sampler: behaviour with a fake ffmpeg
# ---------------------------------------------------------------------------


def _fake_ffmpeg(monkeypatch: pytest.MonkeyPatch, *, frames: int, returncode: int = 0):
    """Replace subprocess.run; write `frames` jpgs into the output directory."""
    calls: list[list[str]] = []

    def _run(cmd, **kwargs):
        calls.append(list(cmd))
        if returncode != 0:
            return subprocess.CompletedProcess(
                cmd, returncode, stdout="", stderr="Invalid data found when processing input"
            )
        out_pattern = Path(cmd[-1])
        for index in range(1, frames + 1):
            (out_pattern.parent / (frame_sampler.FRAME_PATTERN % index)).write_bytes(b"jpeg")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(frame_sampler.subprocess, "run", _run)
    return calls


def test_sampled_frames_carry_nominal_timestamps(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"media")
    _fake_ffmpeg(monkeypatch, frames=3)

    frames = sample_frames(
        ffmpeg_bin="ffmpeg",
        input_path=source,
        out_dir=tmp_path / "frames",
        start_ms=1000,
        end_ms=2000,
        fps=5.0,
    )

    assert [frame.timestamp_ms for frame in frames] == [1000, 1200, 1400]
    assert all(isinstance(frame, SampledFrame) for frame in frames)
    assert all(frame.path.is_file() for frame in frames)


def test_sampling_passes_a_timeout_to_the_subprocess(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"media")
    seen: dict = {}

    def _run(cmd, **kwargs):
        seen.update(kwargs)
        out_pattern = Path(cmd[-1])
        (out_pattern.parent / (frame_sampler.FRAME_PATTERN % 1)).write_bytes(b"jpeg")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(frame_sampler.subprocess, "run", _run)

    sample_frames(
        ffmpeg_bin="ffmpeg",
        input_path=source,
        out_dir=tmp_path / "frames",
        start_ms=0,
        end_ms=1000,
        timeout_seconds=7.5,
    )

    assert seen["timeout"] == 7.5
    assert seen["check"] is False
    assert "shell" not in seen


def test_stale_frames_from_a_previous_clip_are_removed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The filename counter restarts, so a stale frame would be misattributed."""
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"media")
    out_dir = tmp_path / "frames"
    out_dir.mkdir()
    (out_dir / "frame_00099.jpg").write_bytes(b"old")
    _fake_ffmpeg(monkeypatch, frames=1)

    frames = sample_frames(
        ffmpeg_bin="ffmpeg",
        input_path=source,
        out_dir=out_dir,
        start_ms=0,
        end_ms=1000,
    )

    assert len(frames) == 1
    assert not (out_dir / "frame_00099.jpg").exists()


def test_an_ffmpeg_failure_surfaces_its_own_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"media")
    _fake_ffmpeg(monkeypatch, frames=0, returncode=1)

    with pytest.raises(FrameSamplingError) as excinfo:
        sample_frames(
            ffmpeg_bin="ffmpeg",
            input_path=source,
            out_dir=tmp_path / "frames",
            start_ms=0,
            end_ms=1000,
        )

    assert "Invalid data found" in str(excinfo.value)
    assert "code 1" in str(excinfo.value)


def test_a_timeout_is_reported_as_a_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"media")

    def _run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 1))

    monkeypatch.setattr(frame_sampler.subprocess, "run", _run)

    with pytest.raises(FrameSamplingError, match="timed out"):
        sample_frames(
            ffmpeg_bin="ffmpeg",
            input_path=source,
            out_dir=tmp_path / "frames",
            start_ms=0,
            end_ms=1000,
            timeout_seconds=3,
        )


def test_no_frames_produced_is_an_error_not_an_empty_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"media")
    _fake_ffmpeg(monkeypatch, frames=0)

    with pytest.raises(FrameSamplingError, match="produced no frames"):
        sample_frames(
            ffmpeg_bin="ffmpeg",
            input_path=source,
            out_dir=tmp_path / "frames",
            start_ms=0,
            end_ms=1000,
        )


def test_a_missing_source_is_refused_before_ffmpeg_runs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = _fake_ffmpeg(monkeypatch, frames=1)

    with pytest.raises(FrameSamplingError, match="does not exist"):
        sample_frames(
            ffmpeg_bin="ffmpeg",
            input_path=tmp_path / "absent.mp4",
            out_dir=tmp_path / "frames",
            start_ms=0,
            end_ms=1000,
        )

    assert calls == []


def test_pre_cancellation_never_starts_ffmpeg(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import threading

    source = tmp_path / "clip.mp4"
    source.write_bytes(b"media")
    calls = _fake_ffmpeg(monkeypatch, frames=1)
    cancel = threading.Event()
    cancel.set()

    with pytest.raises(SamplingCancelledError):
        sample_frames(
            ffmpeg_bin="ffmpeg",
            input_path=source,
            out_dir=tmp_path / "frames",
            start_ms=0,
            end_ms=1000,
            cancel_event=cancel,
        )

    assert calls == []


def test_the_temporary_directory_is_private_and_removed(tmp_path: Path) -> None:
    with temporary_sample_dir(tmp_path) as frames_dir:
        assert frames_dir.is_dir()
        # Other local users must not be able to read a private recording.
        assert (frames_dir.stat().st_mode & 0o077) == 0
        (frames_dir / "frame_00001.jpg").write_bytes(b"jpeg")
        kept = frames_dir

    assert not kept.exists()


def test_sampling_into_a_missing_parent_creates_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"media")
    _fake_ffmpeg(monkeypatch, frames=1)

    frames = sample_frames(
        ffmpeg_bin="ffmpeg",
        input_path=source,
        out_dir=tmp_path / "deep" / "nested" / "frames",
        start_ms=0,
        end_ms=1000,
    )

    assert len(frames) == 1


# ---------------------------------------------------------------------------
# Gated: the real tools, when this machine has them
# ---------------------------------------------------------------------------


def _make_clip(path: Path, seconds: int = 2) -> None:
    subprocess.run(
        [
            FFMPEG,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c=gray:s=320x240:d={seconds}",
            "-c:v",
            "mpeg4",
            "-y",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
def test_real_ffmpeg_sampling_produces_bounded_frames(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    _make_clip(source, seconds=2)

    with temporary_sample_dir(tmp_path) as frames_dir:
        frames = sample_frames(
            ffmpeg_bin=FFMPEG,
            input_path=source,
            out_dir=frames_dir,
            start_ms=0,
            end_ms=2000,
            fps=5.0,
            max_frames=DEFAULT_MAX_FRAMES,
        )

        # 2 s at 5 FPS is 10 frames; allow the encoder's rounding either way.
        assert 8 <= len(frames) <= 12
        assert all(frame.path.stat().st_size > 0 for frame in frames)
        timestamps = [frame.timestamp_ms for frame in frames]
        assert timestamps == sorted(timestamps)
        assert timestamps[0] == 0


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
def test_real_sampling_respects_the_frame_cap(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    _make_clip(source, seconds=2)

    with temporary_sample_dir(tmp_path) as frames_dir:
        frames = sample_frames(
            ffmpeg_bin=FFMPEG,
            input_path=source,
            out_dir=frames_dir,
            start_ms=0,
            end_ms=2000,
            fps=5.0,
            max_frames=3,
        )

    assert len(frames) == 3


def test_the_installed_opencv_bundles_the_cascade_the_pin_exists_for() -> None:
    """Guard the ``opencv-python<5`` pin against a silently cascade-less wheel.

    OpenCV 5.x ships ``cv2/data/`` containing only ``__init__.py``: the wheel
    installs, ``import cv2`` succeeds, and the detector then finds nothing
    forever. That is a silent wrong answer, not a crash, which is why the pin
    in ``backend/requirements-analysis.txt`` exists and why this test asserts
    the file is really there rather than trusting the version number.

    Skipped when the analysis extra is absent (the lock pins the version in
    that case); it only bites on a machine that does have OpenCV installed.
    """
    try:
        import cv2
    except ImportError:
        pytest.skip("OpenCV (cv2) is not installed; the lock pins its version")

    cascade = Path(cv2.data.haarcascades) / CASCADE_FILENAME
    assert cascade.is_file(), (
        f"cv2 {cv2.__version__} does not bundle {CASCADE_FILENAME}. OpenCV 5.x "
        "dropped the Haar cascades from the wheel; see backend/requirements-analysis.txt."
    )
    assert detector_status() == (True, None)


def test_the_real_detector_analyses_a_frame_without_raising(tmp_path: Path) -> None:
    """Skips unless the analysis extra is installed; never fakes a detection."""
    available, reason = detector_status()
    if not available:
        pytest.skip(f"Real detector not available here: {reason}")

    import cv2  # only reachable when detector_status() said it is installed
    import numpy as np

    # A flat frame has no face. The honest assertion is "runs and reports
    # none", not "finds a face".
    frame = np.full((240, 320, 3), 127, dtype=np.uint8)
    detector = OpenCVHaarDetector()

    observation = detector.detect(frame, timestamp_ms=0)

    assert observation.timestamp_ms == 0
    assert observation.faces == []
    assert cv2.__version__
