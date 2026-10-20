import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DashboardHome } from "../features/dashboard/DashboardHome";
import { Project } from "../types/projects";
import { CapabilitiesResponse } from "../types/capabilities";
import { HealthResponse } from "../types/health";

const mockHealth: HealthResponse = {
  status: "healthy",
  app: "Laqta",
  version: "0.1.0",
  timestamp: "2026-10-19T05:00:00Z",
};

const baseCapabilities: CapabilitiesResponse = {
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
  asr: { faster_whisper: true, whisperx: false },
  llm: { openai_compatible: false },
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
    yt_dlp: { available: false, path: null, version: null, details: "not installed" },
    notice: "URL ingestion is disabled by the operator.",
  },
};

const mockProjects: Project[] = [
  {
    id: "proj_01",
    name: "Arabic Tech Podcast #01",
    created_at: "2026-10-18T10:00:00Z",
    updated_at: "2026-10-19T09:00:00Z",
    media_count: 1,
    media_assets: [
      {
        id: "med_01",
        project_id: "proj_01",
        original_name: "episode_full.mp4",
        size_bytes: 52428800,
        duration_ms: 180000,
        width: 1920,
        height: 1080,
        video_codec: "h264",
        audio_codec: "aac",
        status: "ready",
        created_at: "2026-10-18T10:00:00Z",
      },
    ],
  },
  {
    id: "proj_02",
    name: "AI Coding Stream",
    created_at: "2026-10-17T10:00:00Z",
    updated_at: "2026-10-17T10:00:00Z",
    media_count: 0,
    media_assets: [],
  },
];

const defaultProps = {
  projects: mockProjects,
  capabilities: baseCapabilities,
  health: mockHealth,
  onSelectProject: vi.fn(),
  onOpenCreateModal: vi.fn(),
  onOpenProjects: vi.fn(),
  onDirectVideoDrop: vi.fn().mockResolvedValue(undefined),
  onCreateWorkspace: vi.fn(),
};

describe("DashboardHome", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows real workspace statistics derived from the project data", () => {
    render(<DashboardHome {...defaultProps} />);

    const stats = within(screen.getByTestId("dashboard-stats"));
    expect(stats.getByText("Workspaces").nextElementSibling).toHaveTextContent("2");
    expect(stats.getByText("Media assets").nextElementSibling).toHaveTextContent("1");
    expect(stats.getByText("Footage").nextElementSibling).toHaveTextContent("3m");
    expect(stats.getByText("Local disk").nextElementSibling).toHaveTextContent("50.0 MB");
  });

  it("presents the Laqta brand and the local-only promise in the hero", () => {
    render(<DashboardHome {...defaultProps} />);

    const hero = within(screen.getByTestId("dashboard-hero"));
    expect(hero.getByText(/Laqta transcribes it/)).toBeInTheDocument();
    expect(hero.getByText(/on-device/i)).toBeInTheDocument();
    // The headline sells the outcome, the copy states that it stays local.
    expect(hero.getByText(/vertical Shorts/i)).toBeInTheDocument();
    expect(hero.getByText(/entirely on this machine/i)).toBeInTheDocument();
  });

  it("documents the four local pipeline stages for returning users", () => {
    render(<DashboardHome {...defaultProps} />);

    const pipeline = within(screen.getByRole("region", { name: "How Laqta works" }));
    expect(pipeline.getByText(/1\. Import/)).toBeInTheDocument();
    expect(pipeline.getByText(/2\. Transcribe/)).toBeInTheDocument();
    expect(pipeline.getByText(/3\. Rank/)).toBeInTheDocument();
    expect(pipeline.getByText(/4\. Render/)).toBeInTheDocument();
  });

  it("reports the local engine state honestly instead of assuming it works", () => {
    render(
      <DashboardHome
        {...defaultProps}
        capabilities={{
          ...baseCapabilities,
          asr: { faster_whisper: false, whisperx: false },
          ffmpeg: { ...baseCapabilities.ffmpeg, available: false, version: null },
        }}
      />,
    );

    expect(screen.getByText("no local ASR installed")).toBeInTheDocument();
    expect(screen.getByText("not found in PATH")).toBeInTheDocument();
    // Optional components are labelled as optional, never as working features.
    expect(screen.getByText("local heuristic scoring only")).toBeInTheDocument();
  });

  it("lists the most recent workspaces and opens the selected one", async () => {
    const user = userEvent.setup();
    const onSelectProject = vi.fn();
    render(<DashboardHome {...defaultProps} onSelectProject={onSelectProject} />);

    expect(screen.getByText(/Continue where you left off/i)).toBeInTheDocument();
    expect(screen.getByText("Arabic Tech Podcast #01")).toBeInTheDocument();
    expect(screen.getByText("AI Coding Stream")).toBeInTheDocument();

    await user.click(screen.getByText("AI Coding Stream"));

    expect(onSelectProject).toHaveBeenCalledWith("proj_02");
  });

  it("filters the recent workspaces with the global header search", () => {
    render(<DashboardHome {...defaultProps} globalSearchQuery="coding" />);

    expect(screen.queryByText("Arabic Tech Podcast #01")).not.toBeInTheDocument();
    expect(screen.getByText("AI Coding Stream")).toBeInTheDocument();
  });

  it("shows a hint when the global search matches no workspace", () => {
    render(<DashboardHome {...defaultProps} globalSearchQuery="zzz-not-here" />);

    expect(screen.getByText(/No workspace matches/i)).toBeInTheDocument();
  });

  it("reports the OpenRouter adapter as a hosted provider, never as local", () => {
    render(
      <DashboardHome
        {...defaultProps}
        capabilities={{
          ...baseCapabilities,
          llm: {
            openai_compatible: true,
            provider: "openrouter",
            ranker_enabled: true,
            base_url: "https://openrouter.ai/api/v1",
            model: "minimax/minimax-m3.1-flash:free",
            api_key_configured: true,
            hosted_opt_in: true,
            free_models: ["minimax/minimax-m3.1-flash:free"],
            disclosure:
              "Warning: with a hosted (cloud) LLM provider, portions of your transcript text leave this device.",
          },
        }}
      />,
    );

    expect(screen.getByText(/OpenRouter · minimax\/minimax-m3.1-flash:free/)).toBeInTheDocument();
    // The user must be told that transcript text leaves the device.
    expect(screen.getByText(/leaves this device/i)).toBeInTheDocument();
  });

  it("does not claim a hosted provider is ready without a key", () => {
    render(
      <DashboardHome
        {...defaultProps}
        capabilities={{
          ...baseCapabilities,
          llm: {
            openai_compatible: true,
            provider: "openrouter",
            ranker_enabled: false,
            base_url: "https://openrouter.ai/api/v1",
            model: "minimax/minimax-m3.1-flash:free",
            api_key_configured: false,
            hosted_opt_in: false,
            free_models: [],
            disclosure: null,
          },
        }}
      />,
    );

    expect(screen.getByText("local heuristic scoring only")).toBeInTheDocument();
    expect(screen.queryByText(/OpenRouter ·/)).not.toBeInTheDocument();
  });

  it("shows the getting-started panel when there is no workspace yet", () => {
    render(<DashboardHome {...defaultProps} projects={[]} />);

    expect(screen.getByText(/No projects yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/Continue where you left off/i)).not.toBeInTheDocument();
  });

  it("keeps the YouTube action disabled when URL ingestion is switched off", async () => {
    const user = userEvent.setup();
    render(<DashboardHome {...defaultProps} />);

    const disabledButton = screen.getByTestId("dashboard-youtube-btn-disabled");
    expect(disabledButton).toBeDisabled();
    expect(screen.queryByTestId("dashboard-youtube-btn")).not.toBeInTheDocument();

    // No import dialog may open while the backend gate is closed.
    await user.click(disabledButton);
    expect(screen.queryByTestId("youtube-import-modal")).not.toBeInTheDocument();
  });

  it("opens the gated import dialog when the local gate is open", async () => {
    const user = userEvent.setup();
    render(
      <DashboardHome
        {...defaultProps}
        capabilities={{
          ...baseCapabilities,
          url_ingestion: {
            enabled: true,
            feature_flag: true,
            yt_dlp: {
              available: true,
              path: "/usr/bin/yt-dlp",
              version: "2026.10.19",
              details: "yt-dlp ready",
            },
            notice: null,
          },
        }}
      />,
    );

    await user.click(screen.getByTestId("dashboard-youtube-btn"));

    await waitFor(() => {
      expect(screen.getByText(/Import from YouTube/i)).toBeInTheDocument();
    });
  });

  it("routes the upload CTA to the drop handler", async () => {
    const user = userEvent.setup();
    render(<DashboardHome {...defaultProps} />);

    const input = screen.getByTestId("dashboard-file-input") as HTMLInputElement;
    const file = new File(["data"], "clip.mp4", { type: "video/mp4" });
    await user.upload(input, file);

    await waitFor(() => {
      expect(defaultProps.onDirectVideoDrop).toHaveBeenCalledWith(file);
    });
  });
});
