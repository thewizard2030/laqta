"""Content-addressed cache for transcription results (docs/PERFORMANCE.md.

Why: re-opening a project (changing captions, layout, crop or export
quality) must not re-run ASR. Transcripts are keyed by

1. a streaming SHA-256 fingerprint of the extracted 16 kHz mono WAV plus
   its PCM sample count, and
2. a SHA-256 fingerprint of the transcription settings that can change
   results (model, language, beam, VAD, compute type, provider) plus a
   schema version.

Caveat recorded honestly: the fingerprint covers the *extracted* audio, so
it is invalid if extraction settings change (e.g. a different sample rate
in future code) - the settings fingerprint includes the WAV layout the
decoder expects. Source media edits flow through re-extraction and produce
a different fingerprint.

Cache files live under the Laqta data directory (never inside source code
directories): ``<data_dir>/cache/transcripts/<key>.json``. A purge helper
supports cleanup by age or full wipe.
"""

import hashlib
import json
import time
from pathlib import Path

from app.core.logging import logger

CACHE_SCHEMA_VERSION = 1

# Settings that change the transcription result. Column order matters only
# for readability; the fingerprint uses canonical JSON.
RESULT_SETTINGS_KEYS = (
    "model_size",
    "language",
    "beam_size",
    "vad_filter",
    "compute_type",
    "word_timestamps",
    "profile",
    "provider",
    "wav_sample_rate",
    "wav_channels",
    "cache_schema_version",
)


def fingerprint_file(path: Path, chunk_size: int = 1 << 20) -> tuple[str, int]:
    """Stream SHA-256 of a file without loading it into RAM.

    Returns (hex_digest, byte_length) so callers can bind both content and
    size cheaply.
    """
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def settings_fingerprint(settings_map: dict) -> str:
    """Stable hash of the settings that can change transcription output.

    Unknown settings are ignored (only RESULT_SETTINGS_KEYS participate), so
    unrelated config changes (captions, layout, export quality) never
    invalidate a cached transcript.
    """
    relevant = {k: settings_map.get(k) for k in RESULT_SETTINGS_KEYS}
    canonical = json.dumps(relevant, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_cache_key(audio_path: Path, settings_map: dict) -> str:
    """Content-addressed cache key for one transcription pass."""
    file_digest, size = fingerprint_file(audio_path)
    binding = {
        "audio_sha256": file_digest,
        "audio_bytes": size,
        "settings_sha256": settings_fingerprint(settings_map),
    }
    canonical = json.dumps(binding, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _cache_entry_name() -> str:
    return "cache_entry.json"


def load_cached_transcript(cache_dir: Path, key: str) -> dict | None:
    """Return a cached transcript payload or None on miss/invalid.

    The cache file must contain the matching key and the current schema
    version; anything else is treated as a miss (never auto-deleted - purge
    is explicit via :func:`purge_transcript_cache`).
    """
    safe_key = Path(key).name
    path = cache_dir / f"{safe_key}.json"
    try:
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema_version") != CACHE_SCHEMA_VERSION:
            logger.info(f"Transcript cache miss (schema mismatch): {safe_key}")
            return None
        if data.get("key") != key:
            return None
        result = data.get("result")
        if not isinstance(result, dict) or "segments" not in result:
            logger.warning(f"Transcript cache entry malformed: {safe_key}")
            return None
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to read transcript cache entry {safe_key}: {e}")
        return None


def store_transcript(cache_dir: Path, key: str, settings_map: dict, result: dict) -> Path | None:
    """Persist a transcription result. Returns the cache path (None on failure)."""
    safe_key = Path(key).name
    payload = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "key": key,
        "stored_at": time.time(),
        "settings": {k: settings_map.get(k) for k in RESULT_SETTINGS_KEYS},
        "result": result,
    }
    path = cache_dir / f"{safe_key}.json"
    tmp_path = path.with_suffix(".json.tmp")
    try:
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(path)  # atomic publish
        return path
    except OSError as e:
        logger.warning(f"Failed to store transcript cache entry {safe_key}: {e}")
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def purge_transcript_cache(cache_dir: Path, older_than_days: float | None = None) -> int:
    """Delete cache entries. Returns the number of files removed.

    With ``older_than_days`` only entries older than the cutoff are removed;
    without it the whole cache directory is emptied. Failures are logged and
    skipped so cleanup never breaks other work.
    """
    removed = 0
    cutoff = None
    if older_than_days is not None:
        cutoff = time.time() - max(0.0, float(older_than_days)) * 86400.0
    try:
        entries = list(cache_dir.glob("*.json"))
    except OSError as e:
        logger.warning(f"Cannot list transcript cache dir {cache_dir}: {e}")
        return 0
    for path in entries:
        if path.name.endswith(".tmp"):
            continue
        try:
            if cutoff is not None and path.stat().st_mtime > cutoff:
                continue
            path.unlink(missing_ok=True)
            removed += 1
        except OSError as e:
            logger.warning(f"Failed to purge cache entry {path.name}: {e}")
    return removed
