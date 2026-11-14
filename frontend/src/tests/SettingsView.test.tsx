import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SettingsView } from "../features/settings/SettingsView";
import { api } from "../lib/api/client";
import { CapabilitiesResponse } from "../types/capabilities";
import { SettingsResponse } from "../types/settings";

const mockCapabilities: CapabilitiesResponse = {
  app_name: "Laqta",
  version: "0.1.0",
  local_only: true,
  ffmpeg: {
    available: true,
    path: "/usr/bin/ffmpeg",
    version: "ffmpeg version 7.1.1",
    has_libass: true,
    details: "FFmpeg ready",
  },
  ffprobe: {
    available: true,
    path: "/usr/bin/ffprobe",
    version: "ffprobe version 7.1.1",
    details: "FFprobe ready",
  },
  asr: {
    faster_whisper: true,
    whisperx: false,
  },
  llm: {
    openai_compatible: true,
  },
  hardware: {
    device: "cpu",
    cuda_available: false,
    recommended_worker_concurrency: 1,
  },
  storage: {
    data_dir: "/home/user/.local/share/qatta",
    exists: true,
    writable: true,
  },
  url_ingestion: {
    enabled: false,
    feature_flag: false,
    yt_dlp: {
      available: true,
      path: "/usr/bin/yt-dlp",
      version: "2024.10.07",
      details: null,
    },
    notice: null,
  },
};

const mockSettings: SettingsResponse = {
  app_name: "Laqta",
  version: "0.1.0",
  allow_cloud_apis: false,
  llm_hosted_opt_in: false,
  enable_url_ingestion: false,
  llm_ranker_enabled: false,
  llm_provider: "openrouter",
  llm_base_url: "http://127.0.0.1:11434/v1",
  llm_model: "qwen2.5:7b-instruct",
  llm_openrouter_base_url: "https://openrouter.ai/api/v1",
  llm_openrouter_model: "minimax/minimax-m3.1-flash:free",
  llm_api_key_configured: false,
  redacted_llm_api_key: "<none>",
  llm_openrouter_api_key_configured: true,
  redacted_openrouter_api_key: "sk-o...1234",
  free_models: ["minimax/minimax-m3.1-flash:free"],
  default_transcription_backend: "faster-whisper",
  default_whisper_profile: "fast",
  default_whisper_model: "base",
  fast_whisper_model: "base",
  balanced_whisper_model: "small",
  accurate_whisper_model: "medium",
  default_whisper_device: "cpu",
  default_whisper_compute_type: "int8",
  whisper_vad_filter: true,
  whisper_beam_size: 1,
  whisper_cpu_threads: 4,
  groq_model: "whisper-large-v3-turbo",
  groq_api_key_configured: false,
  redacted_groq_api_key: "<none>",
  assemblyai_api_key_configured: false,
  redacted_assemblyai_api_key: "<none>",
  hf_token_configured: false,
  redacted_hf_token: "<none>",
  clip_alignment_enabled: true,
  clip_alignment_model: "small",
  max_clip_alignment_seconds: 120,
  arabish_initial_prompt: true,
  arabish_prompt_text: "AI, API, SaaS",
  youtube_sub_languages: "ar.*,ar,en.*,en",
  yt_dlp_player_client: "android,ios,web",
  yt_dlp_cookies_path: null,
  yt_dlp_cookies_from_browser: null,
  ffmpeg_timeout_seconds: 300,
  data_dir: "/home/user/.local/share/qatta",
  db_path: "/home/user/.local/share/qatta/qatta.db",
  transcript_cache_enabled: true,
  cached_transcripts_count: 5,
  cached_transcripts_bytes: 1048576,
  disk_total_bytes: 107374182400,
  disk_free_bytes: 53687091200,
  disk_used_bytes: 53687091200,
};

describe("SettingsView & BYOK Studio", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(api, "getSettings").mockResolvedValue(mockSettings);
  });

  it("renders settings header and tabs", async () => {
    render(<SettingsView capabilities={mockCapabilities} />);

    await waitFor(() => {
      expect(screen.getByText(/Studio Settings & Engine/i)).toBeInTheDocument();
    });

    expect(screen.getByRole("tab", { name: /AI & BYOK Keys/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Speech Recognition/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Ingestion & Video/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Storage & Cache/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /System Audit/i })).toBeInTheDocument();
  });

  it("displays and switches between tabs", async () => {
    const user = userEvent.setup();
    render(<SettingsView capabilities={mockCapabilities} />);

    await waitFor(() => {
      expect(screen.getByText(/Master Cloud APIs Switch/i)).toBeInTheDocument();
    });

    // Switch to Speech Recognition
    await user.click(screen.getByRole("tab", { name: /Speech Recognition/i }));
    await waitFor(() => {
      expect(screen.getByText(/Default Speech-to-Text Backend/i)).toBeInTheDocument();
      expect(screen.getByText(/Local Whisper Accuracy Profiles/i)).toBeInTheDocument();
    });

    // Switch to Storage & Cache
    await user.click(screen.getByRole("tab", { name: /Storage & Cache/i }));
    await waitFor(() => {
      expect(screen.getByText(/Disk Storage & Locations/i)).toBeInTheDocument();
      expect(screen.getByText(/Content-Addressed Transcript Cache/i)).toBeInTheDocument();
    });

    // Switch to System Audit
    await user.click(screen.getByRole("tab", { name: /System Audit/i }));
    await waitFor(() => {
      expect(screen.getByText(/System Runtime & Media Capabilities/i)).toBeInTheDocument();
    });
  });

  it("handles provider key testing and saves settings", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "verifyKey").mockResolvedValue({
      ok: true,
      message: "Connected to OpenRouter (15 models found)",
      latency_ms: 240,
    });
    vi.spyOn(api, "updateSettings").mockResolvedValue({
      ...mockSettings,
      allow_cloud_apis: true,
    });

    render(<SettingsView capabilities={mockCapabilities} />);

    await waitFor(() => {
      expect(screen.getByText(/Master Cloud APIs Switch/i)).toBeInTheDocument();
    });

    // Test connection probe
    const testBtn = screen.getByRole("button", { name: /Test Connection/i });
    await user.click(testBtn);

    await waitFor(() => {
      expect(screen.getByText(/Connected to OpenRouter/i)).toBeInTheDocument();
    });

    // Toggle Cloud APIs
    const cloudToggle = screen.getByTestId("toggle-allow-cloud-apis");
    await user.click(cloudToggle);

    expect(screen.getByText(/Unsaved changes/i)).toBeInTheDocument();

    // Click Save
    const saveBtn = screen.getByRole("button", { name: /Save Settings/i });
    await user.click(saveBtn);

    await waitFor(() => {
      expect(api.updateSettings).toHaveBeenCalledWith({ allow_cloud_apis: true });
      expect(screen.queryByText(/Unsaved changes/i)).not.toBeInTheDocument();
    });
  });

  it("handles clearing the transcript cache with confirm dialog", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "clearTranscriptCache").mockResolvedValue({
      cleared_files: 5,
      freed_bytes: 1048576,
      message: "Cleared 5 cached transcripts (1.00 MB freed).",
    });

    render(<SettingsView capabilities={mockCapabilities} />);

    await waitFor(() => {
      expect(screen.getByRole("tab", { name: /Storage & Cache/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("tab", { name: /Storage & Cache/i }));

    await waitFor(() => {
      expect(screen.getByText(/5 files/i)).toBeInTheDocument();
    });

    const clearBtn = screen.getByRole("button", { name: /Clear Transcript Cache/i });
    await user.click(clearBtn);

    // Confirmation dialog should appear
    expect(screen.getByText(/Clear Transcript Cache\?/i)).toBeInTheDocument();

    // Confirm action
    const confirmBtn = screen.getAllByRole("button", { name: /Clear Cache/i })[0];
    await user.click(confirmBtn);

    await waitFor(() => {
      expect(api.clearTranscriptCache).toHaveBeenCalled();
      expect(screen.getByText(/Cleared 5 cached transcripts/i)).toBeInTheDocument();
    });
  });

  it("handles discarding unsaved changes and factory reset", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "resetSettings").mockResolvedValue({
      ...mockSettings,
      allow_cloud_apis: false,
    });

    render(<SettingsView capabilities={mockCapabilities} />);

    await waitFor(() => {
      expect(screen.getByText(/Master Cloud APIs Switch/i)).toBeInTheDocument();
    });

    // Toggle Cloud APIs to create unsaved changes
    const cloudToggle = screen.getByTestId("toggle-allow-cloud-apis");
    await user.click(cloudToggle);

    expect(screen.getByTestId("unsaved-changes-badge")).toBeInTheDocument();

    // Click Discard
    const discardBtn = screen.getByRole("button", { name: /Discard/i });
    await user.click(discardBtn);

    expect(screen.queryByTestId("unsaved-changes-badge")).not.toBeInTheDocument();

    // Click Reset Defaults
    const resetBtn = screen.getByTestId("reset-defaults-btn");
    await user.click(resetBtn);

    await waitFor(() => {
      expect(screen.getByText(/Reset All Settings to Defaults\?/i)).toBeInTheDocument();
    });
    const confirmBtn = screen.getByRole("button", { name: /Reset to Defaults/i });
    await user.click(confirmBtn);

    await waitFor(() => {
      expect(api.resetSettings).toHaveBeenCalled();
    });
  });

  it("supports refreshing system capabilities audit", async () => {
    const user = userEvent.setup();
    const onRefresh = vi.fn().mockResolvedValue(undefined);

    render(<SettingsView capabilities={mockCapabilities} onRefreshCapabilities={onRefresh} />);

    await waitFor(() => {
      expect(screen.getByRole("tab", { name: /System Audit/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("tab", { name: /System Audit/i }));

    await waitFor(() => {
      expect(screen.getByText(/System Runtime & Media Capabilities/i)).toBeInTheDocument();
    });

    const refreshBtn = screen.getByRole("button", { name: /Refresh Audit/i });
    await user.click(refreshBtn);

    expect(onRefresh).toHaveBeenCalledTimes(1);
  });
});
