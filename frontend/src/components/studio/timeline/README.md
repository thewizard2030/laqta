# Timeline

## Overview
Interactive multi-track timeline editor featuring an adaptive time ruler, video filmstrip preview frames, draggable audio waveform playhead, and clickable subtitle/candidate clip blocks.

## Interface
- MultiTrackTimeline.tsx: MultiTrackTimeline - Multi-track timeline coordinating ruler, filmstrip, waveform, and subtitle tracks
- FilmstripTrack.tsx: FilmstripTrack - Visual strip of periodic video frames along the media timeline
- WaveformTrack.tsx: WaveformTrack - Interactive audio waveform visualizer supporting mouse scrubbing and zoom
- SubtitleBlocksTrack.tsx: SubtitleBlocksTrack - Segment blocks representing transcribed speech and candidate intervals

## Invariants
- Time ruler steps adapt dynamically (MAX_RULER_LABELS = 12) to keep tick labels readable regardless of media duration
- Filmstrip preview frames are capped at MAX_FRAMES = 48 to prevent excessive DOM allocations on long media
- Active clip window boundary is visually synchronized across filmstrip, waveform, and subtitle tracks
- Timeline zoom scale is clamped between 1.0 (100%) and 2.5 (250%)

## Side Effects
- Dispatches onSeek callback during mouse scrubbing on ruler and waveform tracks
- Dispatches onSelectSegment when clicking subtitle caption blocks

## Verification
- Run: `npm --prefix frontend test`
