# S05 Ranking

## Overview
Candidate evaluation and prioritization stage defining hard qualitative veto gates and archetype-weighted Clip Potential Score (CPS) ranking.

## Interface
- VetoGates evaluation (dangling context, non-pause boundaries, excessive crosstalk)
- CPSBreakdown scoring (standalone clarity, hook strength, story payoff, value originality, audio dynamics, visual composition, boundary precision)

## Invariants
- Hard veto gates (dangling context, non-pause cut boundaries, excessive crosstalk) strictly precede scoring; failing any gate disqualifies the candidate
- CPS is an explainable heuristic/editorial ranking score (0-100), never a claim of virality prediction or view probability
- Archetype weights dynamically renormalize across measurable component signals without fabricating missing metrics

## Side Effects
- In-memory evaluation of candidates; updates candidate.veto_gates, candidate.cps, and candidate.evidence_log

## Verification
- Run: `pytest tests/`
