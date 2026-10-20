"""Unit tests for media probe detection functions."""

import subprocess
from unittest.mock import patch

from app.services.media.probe import (
    _check_module_installed,
    detect_asr_capabilities,
    detect_ffmpeg,
    detect_ffprobe,
    detect_hardware_capabilities,
)


def test_detect_ffmpeg_missing_binary() -> None:
    """When ffmpeg is not found, should return available=False."""
    with patch("shutil.which", return_value=None):
        cap = detect_ffmpeg()
        assert cap.available is False
        assert cap.path is None
        assert cap.has_libass is False


def test_detect_ffmpeg_timeout() -> None:
    """When ffmpeg times out, should handle exception cleanly."""
    with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        with patch("os.path.exists", return_value=True):
            timeout_err = subprocess.TimeoutExpired(cmd=["ffmpeg"], timeout=3.0)
            with patch("subprocess.run", side_effect=timeout_err):
                cap = detect_ffmpeg()
                assert cap.available is False
                assert "timed out" in (cap.details or "")


def test_detect_ffprobe_missing_binary() -> None:
    """When ffprobe is not found, should return available=False."""
    with patch("shutil.which", return_value=None):
        cap = detect_ffprobe()
        assert cap.available is False
        assert cap.path is None


def test_check_module_installed_nonexistent() -> None:
    """Non-existent module should safely return False."""
    assert _check_module_installed("non_existent_fake_module_xyz") is False


def test_detect_asr_capabilities() -> None:
    """ASR detection returns valid structure without throwing."""
    asr = detect_asr_capabilities()
    assert isinstance(asr.faster_whisper, bool)
    assert isinstance(asr.whisperx, bool)


def test_detect_hardware_capabilities() -> None:
    """Hardware capability returns cpu/cuda and single worker concurrency."""
    hw = detect_hardware_capabilities()
    assert hw.device in ("cpu", "cuda")
    assert isinstance(hw.cuda_available, bool)
    assert hw.recommended_worker_concurrency == 1
