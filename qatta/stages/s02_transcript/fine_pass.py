"""Stage s02_transcript — Pass 2 (Precision Word Alignment on winners).

Given the winning ``ClipCandidate`` objects selected by Stage 05, this
pass slices ONLY ``[clip.start_ms - fine_padding_ms, clip.end_ms +
fine_padding_ms]`` from ``audio_16k.wav`` (default ±2 s of the ~30–60 s
clip, never the full 2-hour source), re-times words with faster-whisper
``word_timestamps=True`` (``vad_filter=False`` so slice-relative offsets
stay valid), then:

1. Populates ``WordToken`` lists inside the utterances overlapping the
   clip (offsets were converted back to absolute source milliseconds).
2. Snaps ``clip.start_ms`` / ``clip.end_ms`` to the first/last detected
   word ± ``snap_pad_ms`` (default 120 ms) of silence padding, so no word
   is ever clipped. ``duration_sec`` is kept consistent with the snapped
   milliseconds by the schema validator.

Failure policy (never block a short): if word alignment fails or no
words are detected for a clip, the clip keeps its original boundaries
and utterances keep their coarse text — the reason is appended to the
candidate's ``evidence_log`` instead of silently pretending alignment
happened.
"""

from __future__ import annotations

import re

import numpy as np

from qatta.core.config import QattaSettings
from qatta.core.pipeline import PipelineError
from qatta.core.schema import (
    ClipCandidate,
    QattaManifest,
    WordToken,
)
from qatta.stages.s02_transcript.fast_pass import (
    TranscriptionAdapter,
    WordTiming,
    audio_total_ms,
    load_pcm_16k,
)

_LATIN_RE = re.compile(r"[A-Za-z]")


def _is_latin_token(word: str) -> bool:
    """True when the token contains Latin letters (Arablish code-switch)."""
    return bool(_LATIN_RE.search(word))


def _clamp_confidence(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


def slice_pcm_ms(pcm: np.ndarray, sr: int, start_ms: int, end_ms: int) -> tuple[np.ndarray, int]:
    """Slice pcm given an inclusive ms window, returning (slice, offset_ms)."""
    total_ms = audio_total_ms(pcm, sr)
    start = max(0, min(start_ms, total_ms))
    end = max(start, min(end_ms, total_ms))
    i0 = int(start * sr / 1000)
    i1 = int(end * sr / 1000)
    return pcm[i0:i1], start


def compute_candidate_alignment(
    candidate: ClipCandidate,
    pcm: np.ndarray,
    sr: int,
    adapter: TranscriptionAdapter,
    padding_ms: int = 2000,
    snap_pad_ms: int = 120,
    language: str | None = None,
    extra_beam_size: int = 2,
    pre_sliced_pcm: np.ndarray | None = None,
    pre_slice_start_ms: int | None = None,
) -> tuple[ClipCandidate, list[WordToken], str | None]:
    """Re-time one candidate's words; return (candidate, word_tokens, note).

    - ``candidate``: the possibly SNAPPED candidate (start/end moved to the
      exact first/last word ± silence padding).
    - ``word_tokens``: absolute-time ``WordToken`` values extracted from
      the slice (empty when alignment found nothing).
    - ``note``: an honest failure/keep-original reason, or ``None``.

    With ``pre_sliced_pcm`` (YouTube captions-first mode) ``pcm`` may be
    empty: the section media downloaded by s05b already covers
    ``[pre_slice_start_ms, +len)`` of the SOURCE timeline, so no slicing
    happens and ``pre_slice_start_ms`` IS the slice offset.
    """
    if pre_sliced_pcm is not None:
        if pre_slice_start_ms is None:
            raise PipelineError(
                "pre_sliced_pcm was provided without pre_slice_start_ms; "
                "the slice offset is mandatory for word-timing math."
            )
        slice_pcm = pre_sliced_pcm
        slice_start = int(pre_slice_start_ms)
        total_ms = slice_start + audio_total_ms(slice_pcm, sr)
    else:
        total_ms = audio_total_ms(pcm, sr)
        slice_pcm, slice_start = slice_pcm_ms(
            pcm,
            sr,
            candidate.start_ms - padding_ms,
            candidate.end_ms + padding_ms,
        )
    if slice_pcm.size == 0:
        return candidate, [], "audio slice for the clip is empty"

    try:
        timed = adapter.transcribe_words(
            slice_pcm,
            sr,
            language=language,
            beam_size=extra_beam_size,
        )
    except Exception as exc:
        return (
            candidate,
            [],
            f"word alignment failed ({type(exc).__name__}); kept original boundaries",
        )

    # Offset-correct: slice-relative -> absolute source milliseconds.
    absolute: list[WordTiming] = [
        WordTiming(
            word=w.word,
            start_ms=slice_start + w.start_ms,
            end_ms=slice_start + w.end_ms,
            confidence=w.confidence,
        )
        for w in timed
    ]
    overlapping = [
        w for w in absolute if w.end_ms > candidate.start_ms and w.start_ms < candidate.end_ms
    ]
    if not overlapping:
        return candidate, [], "no words detected inside the clip slice"

    first, last = overlapping[0], overlapping[-1]
    new_start = max(slice_start, first.start_ms - snap_pad_ms)
    new_end = min(total_ms, last.end_ms + snap_pad_ms)
    if new_end <= new_start:
        return candidate, [], "snap produced inverted boundaries; kept original"

    payload = candidate.model_dump()
    payload["start_ms"] = new_start
    payload["end_ms"] = new_end
    payload["duration_sec"] = (new_end - new_start) / 1000.0
    snapped = candidate.model_validate(payload)

    tokens = [
        WordToken(
            word=w.word,
            start_ms=w.start_ms,
            end_ms=w.end_ms,
            confidence=_clamp_confidence(w.confidence),
            is_latin=_is_latin_token(w.word),
        )
        for w in overlapping
    ]
    return snapped, tokens, None


def _merge_trees_tokens(
    existing: list[tuple[int, int, str, float, bool]],
    extra_rows: list[tuple[int, int, str, float, bool]],
) -> None:
    """Extend an utterance's token tuples, deduplicating exact repeats."""
    seen = {(s, e, w) for s, e, w, _c, _l in existing}
    for row in extra_rows:
        key = (row[0], row[1], row[2])
        if key in seen:
            continue
        seen.add(key)
        existing.append(row)


def _attach_words_to_utterances(
    utterances: list,
    tokens: list[WordToken],
    u_start_hint: dict[str, tuple[int, int]],
) -> dict[str, list[tuple[int, int, str, float, bool]]]:
    """Assign absolute-time tokens to utterances by midpoint containment
    (falling back to the nearest utterance boundary)."""
    by_u_id: dict[str, list[tuple[int, int, str, float, bool]]] = {}
    spans = u_start_hint
    for token in tokens:
        mid = (token.start_ms + token.end_ms) // 2
        contained = [
            (u.u_id, u.start_ms, u.end_ms) for u in utterances if u.start_ms <= mid <= u.end_ms
        ]
        if contained:
            target = contained[0][0]
        elif spans:
            # Nearest-utterance fallback so words at clipped edges still
            # land in a token list instead of being dropped silently.
            target = min(
                spans.items(),
                key=lambda kv: min(
                    abs(token.start_ms - kv[1][1]),
                    abs(token.end_ms - kv[1][0]),
                ),
            )[0]
        else:
            continue
        by_u_id.setdefault(target, []).append(
            (
                token.start_ms,
                token.end_ms,
                token.word,
                token.confidence,
                token.is_latin,
            )
        )
    return by_u_id


def align_winner_words(
    manifest: QattaManifest,
    winner_clip_ids: list[str],
    settings: QattaSettings,
    adapter: TranscriptionAdapter | None = None,
) -> QattaManifest:
    """Run Pass 2 for ONLY the winning candidates referenced by clip id.

    Returns a manifest clone with:
    - snapped candidates replacing their old versions,
    - ``WordToken`` lists populated in the overlapped utterances,
    - honest ``evidence_log`` notes when a clip could not be aligned.
    """
    _subs_first = manifest.transcript_source == "youtube_subs_first"
    if (
        not manifest.audio_16k_path
        and not any(c.section_audio_16k_path for c in manifest.candidates)
        and not _subs_first
    ):
        raise PipelineError(
            "No audio source for Pass 2: neither audio_16k.wav (s01) nor "
            "any downloaded clip section (s05b) exists in the manifest."
        )
    full_pcm, sr = (
        load_pcm_16k(manifest.audio_16k_path)
        if manifest.audio_16k_path
        else (np.zeros(0, dtype=np.float32), 16000)
    )
    profile = (manifest.language_profile or "").lower()
    language: str | None = None
    if profile.startswith("ar"):
        language = "ar"
    elif profile.startswith("en"):
        language = "en"

    owned = adapter is None
    adapter = adapter or _default_word_adapter(settings)
    try:
        candidates = {c.clip_id: c for c in manifest.candidates}
        missing = [cid for cid in winner_clip_ids if cid not in candidates]
        if missing:
            raise PipelineError(
                "Pass 2 winners reference unknown clip ids: "
                f"{missing}. Existing clips: {sorted(candidates)}."
            )

        by_u_id_tokens: dict[str, list[tuple[int, int, str, float, bool]]] = {}
        u_hint = {u.u_id: (u.start_ms, u.end_ms) for u in manifest.atomic_utterances}
        updated_candidates: dict[str, ClipCandidate] = {}
        notes: list[str] = []

        for clip_id in winner_clip_ids:
            candidate = candidates[clip_id]
            pre_sliced = None
            pre_start = None
            local_pcm = full_pcm
            if candidate.section_audio_16k_path:
                # YouTube captions-first mode: align from the clip's own
                # downloaded section (offset-corrected by s05b metadata).
                local_pcm, _ = load_pcm_16k(candidate.section_audio_16k_path)
                pre_sliced = local_pcm
                pre_start = int(candidate.section_start_ms or 0)
            if pre_sliced is None and not manifest.audio_16k_path:
                payload = candidate.model_dump()
                payload.setdefault("evidence_log", []).append(
                    "pass2: no audio source for this clip "
                    "(no downloaded section); kept original boundaries"
                )
                updated_candidates[clip_id] = candidate.model_validate(payload)
                notes.append(f"{clip_id}: no audio source; kept original boundaries")
                continue
            snapped, tokens, note = compute_candidate_alignment(
                candidate,
                local_pcm,
                sr,
                adapter,
                padding_ms=settings.fine_padding_ms,
                snap_pad_ms=settings.snap_pad_ms,
                language=language,
                extra_beam_size=settings.fine_beam_size,
                pre_sliced_pcm=pre_sliced,
                pre_slice_start_ms=pre_start,
            )
            payload = snapped.model_dump()
            if note:
                notes.append(note)
                payload.setdefault("evidence_log", []).append(f"pass2: {note}")
            else:
                payload.setdefault("evidence_log", []).append(
                    "pass2: word timing snapped to acoustic boundaries"
                )
            updated_candidates[clip_id] = snapped.model_validate(payload)
            for u_key, rows in _attach_words_to_utterances(
                manifest.atomic_utterances, tokens, u_hint
            ).items():
                _merge_trees_tokens(by_u_id_tokens.setdefault(u_key, []), rows)

        # Build the updated manifest clone.
        updated_utterances = []
        for utterance in manifest.atomic_utterances:
            rows = by_u_id_tokens.get(utterance.u_id, [])
            if rows:
                payload = utterance.model_dump()
                payload["words"] = [
                    {
                        "word": w,
                        "start_ms": s,
                        "end_ms": e,
                        "confidence": c,
                        "is_latin": latin,
                    }
                    for s, e, w, c, latin in sorted(rows, key=lambda r: r[0])
                ]
                updated_utterances.append(utterance.model_validate(payload))
            else:
                updated_utterances.append(utterance)

        new_candidates = [updated_candidates.get(c.clip_id, c) for c in manifest.candidates]
        data = manifest.model_dump()
        data["atomic_utterances"] = [u.model_dump() for u in updated_utterances]
        data["candidates"] = [c.model_dump() for c in new_candidates]
        return manifest.model_validate(data)
    finally:
        if owned:
            adapter.close()


def _default_word_adapter(settings: QattaSettings) -> TranscriptionAdapter:
    """Pass 2 always runs locally (no cloud word-timing path exists)."""
    from qatta.stages.s02_transcript.fast_pass import (
        LocalTurboBatchedTranscriber,
    )

    return LocalTurboBatchedTranscriber(
        model_name=settings.turbo_model,
        batch_size=settings.turbo_batch_size,
        compute_type=settings.turbo_compute_type,
        beam_size=settings.fine_beam_size,
    )


def run_fine_alignment_stage(
    manifest: QattaManifest,
    winner_clip_ids: list[str],
    settings: QattaSettings | None = None,
    adapter: TranscriptionAdapter | None = None,
) -> QattaManifest:
    """Stage entry point: run Pass 2 on the given winning clip ids.

    With an empty ``winner_clip_ids`` the manifest is returned unchanged
    (nothing to align — callers from Stage 05 always pass the winners).
    """
    settings = settings or QattaSettings()
    if not winner_clip_ids:
        return manifest
    return align_winner_words(manifest, winner_clip_ids, settings, adapter)


def register(orchestrator, adapter: TranscriptionAdapter | None = None) -> None:
    """Attach ``s02b_fine_alignment``; adapter injectable for tests."""

    @orchestrator.stage("s02b_fine_alignment")
    def _stage(manifest: QattaManifest) -> QattaManifest:
        winners = [c.clip_id for c in manifest.candidates]
        return run_fine_alignment_stage(manifest, winners, orchestrator.settings, adapter=adapter)
