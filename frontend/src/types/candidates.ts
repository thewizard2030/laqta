/**
 * Types for clip candidates (PRD §5 FR-04/FR-05) — mirrors backend
 * app/schemas/candidates.py honestly, including unavailable-evidence state.
 */

export type CandidateStatus = "suggested" | "penalized" | "rejected";

export interface ComponentScore {
  key: string;
  label: string;
  score: number | null;
  nominal_weight: number;
  effective_weight: number | null;
  available: boolean;
  rationale: string;
}

export interface Candidate {
  id: string;
  media_id: string;
  transcript_id: string;
  start_ms: number;
  end_ms: number;
  duration_ms: number;
  status: CandidateStatus;
  cps: number;
  cps_interpretation: string;
  title: string | null;
  hook: string | null;
  transcript_span_ids: string[];
  feature_scores: ComponentScore[];
  unavailable_features: string[];
  rationale: string[];
  created_at: string;
  boundary_edited?: boolean;
}

export interface CandidateGenerationResponse {
  media_id: string;
  transcript_id: string;
  candidates: Candidate[];
  warnings: string[];
  scoring_notice: string;
  ranking_method: "baseline" | "llm_reranked";
  ranking_provider: string | null;
}

export interface CandidateUpdateRequest {
  start_ms: number;
  end_ms: number;
  title?: string | null;
  hook?: string | null;
}
