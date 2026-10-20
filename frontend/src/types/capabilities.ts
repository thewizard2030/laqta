export interface BinaryCapability {
  available: boolean;
  path: string | null;
  version: string | null;
  details: string | null;
}

export interface FFmpegCapability extends BinaryCapability {
  has_libass: boolean;
}

export interface AsrCapabilities {
  faster_whisper: boolean;
  whisperx: boolean;
}

export interface LlmCapabilities {
  /** Whether local OpenAI-compatible endpoints can be called. */
  openai_compatible?: boolean;
  /** Configured adapter: "openai_compatible" (local) or "openrouter" (hosted). */
  provider?: string;
  /** Whether LLM reranking is enabled (the deterministic baseline is default). */
  ranker_enabled?: boolean;
  /** Configured endpoint (no secrets). */
  base_url?: string | null;
  /** Configured model id (no secrets). */
  model?: string | null;
  /** Whether an API key is configured (boolean only, never the key). */
  api_key_configured?: boolean;
  /** Whether a hosted provider is opted in; requires the UI disclosure. */
  hosted_opt_in?: boolean;
  /** Zero-price model ids the hosted gateway offers (informational). */
  free_models?: string[];
  /** Disclosure shown when transcript text leaves the device. */
  disclosure?: string | null;
}

export interface HardwareCapabilities {
  device: string;
  cuda_available: boolean;
  recommended_worker_concurrency: number;
}

export interface StorageCapabilities {
  data_dir: string;
  exists: boolean;
  writable: boolean;
}

export interface UrlIngestionCapabilities {
  /** True only when the operator flag is on AND yt-dlp is installed. */
  enabled: boolean;
  /** QATTA_ENABLE_URL_INGESTION operator flag state. */
  feature_flag: boolean;
  yt_dlp: BinaryCapability;
  /** Honest explanation of the current (possibly partial) state. */
  notice: string | null;
}

export interface CapabilitiesResponse {
  app_name: string;
  version: string;
  local_only: boolean;
  ffmpeg: FFmpegCapability;
  ffprobe: BinaryCapability;
  asr: AsrCapabilities;
  llm: LlmCapabilities;
  hardware: HardwareCapabilities;
  storage: StorageCapabilities;
  url_ingestion: UrlIngestionCapabilities;
}
