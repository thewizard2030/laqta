/**
 * Types for user configuration, BYOK secrets, and connection probes.
 */

export interface SettingsResponse {
  app_name: string;
  version: string;

  // Cloud & Policies
  allow_cloud_apis: boolean;
  llm_hosted_opt_in: boolean;
  enable_url_ingestion: boolean;

  // LLM & Reasoning (BYOK)
  llm_ranker_enabled: boolean;
  llm_provider: string;
  llm_base_url: string;
  llm_model: string;
  llm_openrouter_base_url: string;
  llm_openrouter_model: string;
  llm_api_key_configured: boolean;
  redacted_llm_api_key: string;
  llm_openrouter_api_key_configured: boolean;
  redacted_openrouter_api_key: string;
  free_models: string[];

  // Speech Recognition (ASR)
  default_transcription_backend: string;
  default_whisper_profile: string;
  default_whisper_model: string;
  fast_whisper_model: string;
  balanced_whisper_model: string;
  accurate_whisper_model: string;
  default_whisper_device: string;
  default_whisper_compute_type: string;
  whisper_vad_filter: boolean;
  whisper_beam_size: int;
  whisper_cpu_threads: int;

  // Cloud Transcription (BYOK)
  groq_model: string;
  groq_api_key_configured: boolean;
  redacted_groq_api_key: string;
  assemblyai_api_key_configured: boolean;
  redacted_assemblyai_api_key: string;
  hf_token_configured: boolean;
  redacted_hf_token: string;

  // Arabic & Alignment
  clip_alignment_enabled: boolean;
  clip_alignment_model: string;
  max_clip_alignment_seconds: number;
  arabish_initial_prompt: boolean;
  arabish_prompt_text: string;

  // Ingestion
  youtube_sub_languages: string;
  yt_dlp_player_client: string;
  yt_dlp_cookies_path: string | null;
  yt_dlp_cookies_from_browser: string | null;
  ffmpeg_timeout_seconds: number;

  // Storage & Cache
  data_dir: string;
  db_path: string;
  transcript_cache_enabled: boolean;
  cached_transcripts_count: number;
  cached_transcripts_bytes: number;
  disk_total_bytes: number;
  disk_free_bytes: number;
  disk_used_bytes: number;
}

export interface SettingsUpdateRequest {
  allow_cloud_apis?: boolean;
  llm_hosted_opt_in?: boolean;
  enable_url_ingestion?: boolean;

  llm_ranker_enabled?: boolean;
  llm_provider?: string;
  llm_base_url?: string;
  llm_model?: string;
  llm_api_key?: string;
  llm_openrouter_base_url?: string;
  llm_openrouter_model?: string;
  llm_openrouter_api_key?: string;

  default_transcription_backend?: string;
  default_whisper_profile?: string;
  default_whisper_model?: string;
  fast_whisper_model?: string;
  balanced_whisper_model?: string;
  accurate_whisper_model?: string;
  default_whisper_device?: string;
  default_whisper_compute_type?: string;
  whisper_vad_filter?: boolean;
  whisper_beam_size?: number;
  whisper_cpu_threads?: number;

  groq_api_key?: string;
  groq_model?: string;
  assemblyai_api_key?: string;
  hf_token?: string;

  clip_alignment_enabled?: boolean;
  clip_alignment_model?: string;
  max_clip_alignment_seconds?: number;
  arabish_initial_prompt?: boolean;
  arabish_prompt_text?: string;

  youtube_sub_languages?: string;
  yt_dlp_player_client?: string;
  yt_dlp_cookies_path?: string | null;
  yt_dlp_cookies_from_browser?: string | null;
  ffmpeg_timeout_seconds?: number;

  transcript_cache_enabled?: boolean;
}

export interface VerifyKeyRequest {
  provider: string;
  api_key?: string;
  base_url?: string;
  model?: string;
}

export interface VerifyKeyResponse {
  ok: boolean;
  message: string;
  latency_ms: number;
  details?: Record<string, unknown>;
  models_found?: string[];
}

export interface ClearCacheResponse {
  cleared_files: number;
  freed_bytes: number;
  message: string;
}

type int = number;
