# Candidates

## Overview
Deterministic candidate segment generator deriving video cut windows strictly from transcript boundaries, pause intervals, and sentence-ending punctuation.

## Interface
- app.services.candidates.generator:CandidateGenerationError
- app.services.candidates.generator:BoundaryUnit
- app.services.candidates.generator:CandidateDraft
- app.services.candidates.generator:ScoredCandidate
- app.services.candidates.generator:CandidateGenerationResult
- app.services.candidates.generator:TERMINAL_CHARS: tuple[str, ...]
- app.services.candidates.generator:make_candidate_id(transcript_id: str, start_ms: int, end_ms: int) -> str
- app.services.candidates.generator:build_boundary_units(segments: list[TranscriptSegment], word_timestamps_available: bool, media_duration_ms: int, warnings: list[str]) -> list[BoundaryUnit]
- app.services.candidates.generator:generate_candidates(transcript_id: str, segments: list[TranscriptSegment], word_timestamps_available: bool, media_duration_ms: int, config: ScoringConfig | None = None) -> CandidateGenerationResult

## Invariants
- No hallucinated timestamps: candidate start/end boundaries originate strictly from observed transcript words, sentences, or segment limits [generator.py:build_boundary_units]
- All candidate time spans are clamped to the known media duration [0, media_duration_ms] [generator.py:build_boundary_units]
- Candidate IDs are deterministic 12-char SHA-256 digests derived from transcript ID and time coordinates [generator.py:make_candidate_id]
- Transparent precision: when word timestamps are unavailable, boundaries fall back to segment edges and low_boundary_precision flag is set [generator.py:_make_draft]
- De-duplication enforces maximum overlap IoU (default 0.5) and maximum text Jaccard similarity (default 0.8) [generator.py:generate_candidates]

## Side Effects
- None (pure in-memory deterministic calculation) [generator.py]

## Verification
- Run: `pytest backend/tests`
