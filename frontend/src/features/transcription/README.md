# Transcription

## Overview
Speech transcription viewer and job launcher, supporting faster-whisper CPU profiles (fast, balanced, accurate, custom), timestamp granularity inspection (word vs segment), multi-run historical transcripts selection, and full text vs segment view modes.

## Interface
- TranscriptViewer.tsx: TranscriptViewer - Interactive transcript viewer with search, timestamp sync, and profile launcher

## Invariants
- Fallback to 'fake' provider when faster-whisper is not installed in local backend environment
- Full-text and segment views display bidirectional text with RTL/LTR directional support based on language
- Word-level timestamps are only exposed when available in transcript data

## Side Effects
- Dispatches transcription request via onStartTranscription callback

## Verification
- Run: `npm --prefix frontend test`
