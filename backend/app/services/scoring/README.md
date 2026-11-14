# Scoring

## Overview
Deterministic Clip Potential Score (CPS) calculation across 7 heuristic components and optional LLM-assisted reranking with prompt injection defenses.

## Interface
- app.services.scoring.baseline:DEFAULT_WEIGHTS: dict[str, float]
- app.services.scoring.baseline:COMPONENT_LABELS: dict[str, str]
- app.services.scoring.baseline:CPS_INTERPRETATION: str
- app.services.scoring.baseline:ComponentScore
- app.services.scoring.baseline:ScoringResult
- app.services.scoring.baseline:ScoringConfig
- app.services.scoring.baseline:score_candidate(...) -> ScoringResult
- app.services.scoring.baseline:jaccard_text_similarity(a: str, b: str) -> float
- app.services.scoring.ranker:ClipRanker(ABC)
- app.services.scoring.ranker:BaselineClipRanker(ClipRanker)
- app.services.scoring.ranker:LLMClipRanker(ClipRanker)
- app.services.scoring.ranker:RankCandidateInput
- app.services.scoring.ranker:RankedClip
- app.services.scoring.ranker:RankedSet
- app.services.scoring.ranker:RankingValidationError

## Invariants
- Editorial heuristic score only: CPS is a 0-100 heuristic editorial score and explicitly never represents a virality or view-count probability [baseline.py:CPS_INTERPRETATION]
- Missing modality integrity: unmeasured signals (e.g. visual composition, audio clarity) are surfaced as available=False with an explicit rationale and excluded from weight renormalization rather than defaulted to zero [baseline.py:score_candidate]
- Prompt injection mitigation: transcript excerpts are enclosed within <transcript_evidence> XML tags and treated as untrusted data in LLM prompts [ranker.py:SYSTEM_PROMPT]
- Universal fallback: LLM reranking failures (timeouts, schema validation errors, network issues) silently fall back to the deterministic baseline order [ranker.py:LLMClipRanker.rank]
- LLM never invents timestamps or candidate IDs: candidates and boundaries are immutable during ranking [ranker.py:LLMClipRanker.rank]

## Side Effects
- Local CPU computation for deterministic baseline scoring [baseline.py]
- Outbound HTTP requests to configured LLM providers when LLMClipRanker is invoked [ranker.py:LLMClipRanker]

## Verification
- Run: `pytest backend/tests`
