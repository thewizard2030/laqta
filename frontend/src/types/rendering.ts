/**
 * Rendering and caption artifact types matching backend schemas (PRD §5 FR-08/FR-09).
 */

export type LayoutMode = "center_crop" | "blurred_background";
export type QualityPreset = "high" | "cpu_friendly";
export type CaptionFormatForRender = "ass" | "srt" | "none";
export type CaptionPosition = "bottom" | "middle" | "top";

export interface CaptionStyleSettings {
  font_name?: string;
  font_size?: number;
  bold?: boolean;
  foreground_color?: string;
  highlight_color?: string;
  outline_color?: string;
  outline_width?: number;
  shadow_depth?: number;
  position?: CaptionPosition;
  margin_v?: number;
  margin_h?: number;
  max_chars_per_line?: number;
  max_lines?: number;
  karaoke?: boolean;
}

export interface RenderRequest {
  layout?: LayoutMode;
  quality?: QualityPreset;
  caption_format?: CaptionFormatForRender;
  style?: CaptionStyleSettings;
  overwrite?: boolean;
}

export interface RenderedClipResponse {
  id: string;
  candidate_id: string;
  media_id: string;
  output_path: string;
  width: number;
  height: number;
  duration_ms: number;
  size_bytes: number;
  render_config_json?: string | null;
  created_at: string;
  extra?: Record<string, unknown> | null;
}

export interface CaptionArtifact {
  kind: "srt" | "ass" | "mp4" | "render_log" | "render_config";
  path: string;
  size_bytes: number;
  created_at: string;
}

export interface CandidateArtifactsResponse {
  candidate_id: string;
  media_id: string;
  captions: CaptionArtifact[];
  rendered_clips: CaptionArtifact[];
  warnings: string[];
}

export interface CaptionGenerationRequest {
  style?: CaptionStyleSettings;
  formats?: ("srt" | "ass")[];
}

export interface CandidateCaptionsResponse {
  candidate_id: string;
  media_id: string;
  transcript_id: string;
  srt_path?: string | null;
  ass_path?: string | null;
  timing_granularity: "word" | "segment";
  karaoke_used: boolean;
  warnings: string[];
  style: CaptionStyleSettings;
  created_at: string;
}
