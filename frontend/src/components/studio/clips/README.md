# Clips

## Overview
AI-suggested candidate clip list and transcript browser panel, featuring explainable Clip Potential Score (CPS) ranking, chronological sorting, filter pills, pagination, and clip card items with real preview thumbnails.

## Interface
- SuggestedClipsList.tsx: SuggestedClipsList - Container for candidate clips list, filtering, and pagination
- ClipCardItem.tsx: ClipCardItem - Individual clip card component displaying CPS score, rationale pill, duration, and thumbnail

## Invariants
- ClipCardItem is memoized with React.memo to prevent unnecessary re-renders during periodic 1.5s background job polling
- CPS scores are displayed as 0-100 heuristic scores derived from transcript evidence with deterministic rationales and no LLM claims on baseline
- Thumbnails display real extracted frames from /api/media/{mediaId}/candidates/{candidateId}/thumbnail with deterministic hue gradient fallback on failure
- Pagination mounts cards in batches of 20 (CLIPS_PAGE_SIZE) to ensure responsive rendering of long clip lists

## Side Effects
- Fires selection callback onSelectCandidate to switch active studio clip
- Dispatches onSeekSegment to jump timeline playhead to transcript segment start
- Invokes onStartTranscription and onGenerateCandidates API workflows

## Verification
- Run: `npm --prefix frontend test`
