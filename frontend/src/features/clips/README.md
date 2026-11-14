# Clips

## Overview
Candidate clip review and boundary tuning interface (PRD FR-04/FR-05), presenting heuristic Clip Potential Scores (CPS 0-100), transcript-aligned segment evidence, inline boundary trimming, and score explanations.

## Interface
- CandidatesPanel.tsx: CandidatesPanel - Candidate clip browser with CPS ranking and transcript verification
- CandidatesPanel.tsx: LoadState, TranscriptionJobState - Asynchronous job loading state types
- CandidateCard.tsx: CandidateCard - Candidate clip summary card showing CPS score breakdown and trimming actions
- CandidateCard.tsx: REVIEW_NOTICE - Disclaimer text regarding heuristic editorial scoring vs viral prediction

## Invariants
- Zero synthetic/mock clips: renders truthful empty/failed states if transcription has not run or failed
- CPS is explicitly documented as a heuristic editorial quality score, not a views prediction
- Boundary edits are validated on-client via validateBoundaryEdit before submitting to PATCH /api/candidates/{candidateId}

## Side Effects
- Fetches candidate list from GET /api/media/{mediaId}/candidates
- Triggers candidate generation via POST /api/media/{mediaId}/candidates
- Updates clip boundaries via PATCH /api/candidates/{candidateId}

## Verification
- Run: `npm --prefix frontend test`
