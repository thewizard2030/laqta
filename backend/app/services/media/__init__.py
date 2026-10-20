"""Media processing, signature validation, and probe services for Laqta."""

from app.services.media.audio import (
    AudioExtractionError,
    JobCancelledError,
    build_audio_extraction_command,
    clean_intermediate_audio,
    extract_audio_16k,
)
from app.services.media.probe import (
    MediaProbeError,
    MediaProbeResult,
    detect_capabilities,
    detect_ffmpeg,
    detect_ffprobe,
    probe_media_file,
)
from app.services.media.signature import validate_media_signature

__all__ = [
    "detect_capabilities",
    "detect_ffmpeg",
    "detect_ffprobe",
    "probe_media_file",
    "validate_media_signature",
    "MediaProbeResult",
    "MediaProbeError",
    "AudioExtractionError",
    "JobCancelledError",
    "build_audio_extraction_command",
    "extract_audio_16k",
    "clean_intermediate_audio",
]
