"""Tests for the sha256+FPM-based content-addressed transcript cache.

Validates:
- Deterministic fingerprinting (streamed, memory-safe) and stable settings hash.
- Independent settings changes (captions/layout/export quality analogues are
  not part of the fingerprint) never invalidate; transcription-relevant
  settings (model, language, beam, VAD, compute, word timestamps, profile)
  always invalidate.
- Store/load round trip, schema-version gating, malformed entries are misses.
- Purge honors age filtering.
"""

import json
import time
from pathlib import Path

from app.services.transcription.cache import (
    CACHE_SCHEMA_VERSION,
    compute_cache_key,
    fingerprint_file,
    load_cached_transcript,
    purge_transcript_cache,
    settings_fingerprint,
    store_transcript,
)


def _write_wav(tmp_path: Path, pattern: bytes) -> Path:
    path = tmp_path / "audio.wav"
    path.write_bytes(b"RIFF" + b"WAVE fmt " + pattern)
    return path


def test_fingerprint_deterministic_and_content_sensitive(tmp_path: Path) -> None:
    wav = _write_wav(tmp_path, b"\x01" * 4096)
    digest1, size = fingerprint_file(wav)
    digest2, size2 = fingerprint_file(wav)
    assert digest1 == digest2
    assert size == size2 == wav.stat().st_size

    changed = _write_wav(tmp_path, b"\x00" * 4096)
    digest3, _ = fingerprint_file(changed)
    assert digest3 != digest1


def test_cache_key_stable_and_sensitive_to_settings(tmp_path: Path) -> None:
    wav = _write_wav(tmp_path, b"\x01" * 256)
    base = {"model_size": "base", "language": "en"}
    key1 = compute_cache_key(wav, base)
    key2 = compute_cache_key(wav, dict(base))
    assert key1 == key2  # stable across calls

    key_model = compute_cache_key(wav, {**base, "model_size": "small"})
    assert key_model != key1

    key_lang = compute_cache_key(wav, {**base, "language": "ar"})
    assert key_lang != key1

    key_beam = compute_cache_key(wav, {**base, "beam_size": 5})
    assert key_beam != key1

    key_vad = compute_cache_key(wav, {**base, "vad_filter": True})
    assert key_vad != key1

    # Unrelated settings MUST NOT change the key: re-captioning, layout and
    # export-quality changes reuse the cached transcript (requirement).
    key_unrelated = compute_cache_key(
        wav, {**base, "caption_font_size": 64, "layout": "center_crop", "crf": 20}
    )
    assert key_unrelated == key1

    # Different audio => different key even with identical settings.
    wav2 = _write_wav(tmp_path, b"\x02" * 256)
    assert compute_cache_key(wav2, base) != key1


def test_settings_fingerprint_ignores_unknown_keys() -> None:
    base = {"model_size": "base", "language": None}
    assert settings_fingerprint(base) == settings_fingerprint({**base, "anything_else": "ignored"})


def test_store_and_load_round_trip(tmp_path: Path) -> None:
    key = "a" * 64
    result = {
        "language": "ar",
        "language_probability": 0.99,
        "duration": 12.5,
        "text": "مرحبا",
        "segments": [{"id": "seg_0001", "start": 0.0, "end": 1.0, "text": "مرحبا"}],
        "word_timestamps_available": False,
        "timing_granularity": "segment",
        "provider": "fake",
        "model": "base",
    }
    path = store_transcript(tmp_path, key, {"model_size": "base"}, result)
    assert path is not None and path.name == f"{key}.json"

    loaded = load_cached_transcript(tmp_path, key)
    assert loaded is not None
    assert loaded["schema_version"] == CACHE_SCHEMA_VERSION
    assert loaded["key"] == key
    assert loaded["result"]["text"] == result["text"]
    assert loaded["result"]["segments"][0]["id"] == "seg_0001"


def test_cache_miss_on_unknown_key(tmp_path: Path) -> None:
    assert load_cached_transcript(tmp_path, "b" * 64) is None


def test_cache_miss_on_corrupt_entry(tmp_path: Path) -> None:
    key = "c" * 64
    (tmp_path / f"{key}.json").write_text("{not json", encoding="utf-8")
    assert load_cached_transcript(tmp_path, key) is None


def test_cache_miss_on_wrong_key_binding(tmp_path: Path) -> None:
    key = "d" * 64
    (tmp_path / f"{key}.json").write_text(
        json.dumps(
            {
                "schema_version": CACHE_SCHEMA_VERSION,
                "key": "other",
                "result": {"segments": []},
            }
        ),
        encoding="utf-8",
    )
    assert load_cached_transcript(tmp_path, key) is None


def test_cache_miss_on_outdated_schema(tmp_path: Path) -> None:
    key = "e" * 64
    (tmp_path / f"{key}.json").write_text(
        json.dumps(
            {
                "schema_version": CACHE_SCHEMA_VERSION - 1,
                "key": key,
                "result": {"segments": []},
            }
        ),
        encoding="utf-8",
    )
    assert load_cached_transcript(tmp_path, key) is None


def test_purge_by_age(tmp_path: Path) -> None:
    key_old, key_new = "f" * 64, "0" * 64
    old = tmp_path / f"{key_old}.json"
    new = tmp_path / f"{key_new}.json"
    old.write_text("{}", encoding="utf-8")
    new.write_text("{}", encoding="utf-8")
    aged = time.time() - 48 * 3600
    os_utime = aged
    import os

    os.utime(old, (os_utime, os_utime))

    removed = purge_transcript_cache(tmp_path, older_than_days=1)
    assert removed == 1
    assert not old.exists()
    assert new.exists()

    removed_all = purge_transcript_cache(tmp_path)
    assert removed_all == 1
    assert not new.exists()
