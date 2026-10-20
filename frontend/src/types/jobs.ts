/**
 * Job status and response types (PRD §5 FR-10).
 */

export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export type JobType =
  | "audio_extraction"
  | "transcription"
  | "candidate_generation"
  | "render"
  | "multimodal"
  | "pipeline";

export interface JobResponse {
  id: string;
  project_id: string;
  media_id: string | null;
  type: string;
  status: JobStatus;
  stage: string;
  progress: number;
  /**
   * True when `progress` cannot be reliably estimated for the current stage
   * (e.g. model loading, clip alignment). UIs should then display the stage
   * name and elapsed time instead of a percent — the backend refuses to
   * fabricate completion percentages.
   */
  indeterminate?: boolean;
  error_code: string | null;
  error_message: string | null;
  config_json: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}
