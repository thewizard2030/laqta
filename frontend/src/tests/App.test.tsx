import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "../App";
import { api } from "../lib/api/client";
import { CapabilitiesResponse } from "../types/capabilities";
import { HealthResponse } from "../types/health";
import { Project } from "../types/projects";

const mockHealthData: HealthResponse = {
  status: "healthy",
  app: "Laqta",
  version: "0.1.0",
  timestamp: "2026-10-18T05:00:00Z",
  worker: "running",
};

const mockCapabilitiesData: CapabilitiesResponse = {
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
    faster_whisper: false,
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
    yt_dlp: { available: false, path: null, version: null, details: "not installed" },
    notice: "URL ingestion is disabled pending PRD FR-12 platform-policy/rights review.",
  },
};

const mockProjectWithMedia: Project = {
  id: "proj_alpha",
  name: "Arabic Tech Podcast #01",
  created_at: "2026-10-18T05:00:00Z",
  updated_at: "2026-10-18T05:00:00Z",
  media_count: 1,
  media_assets: [
    {
      id: "med_123",
      project_id: "proj_alpha",
      original_name: "podcast_full.mp4",
      size_bytes: 15000000,
      duration_ms: 125000,
      width: 1920,
      height: 1080,
      video_codec: "h264",
      audio_codec: "aac",
      status: "ready",
      created_at: "2026-10-18T05:00:00Z",
    },
  ],
};

describe("App Component", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders privacy banner, dashboard home and empty state when no projects exist", async () => {
    vi.spyOn(api, "getHealth").mockResolvedValue(mockHealthData);
    vi.spyOn(api, "getCapabilities").mockResolvedValue(mockCapabilitiesData);
    vi.spyOn(api, "getProjects").mockResolvedValue([]);

    render(<App />);

    expect(screen.getByTestId("loading-skeleton")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/100% Local Processing & Privacy Guarantee/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/No projects yet/i)).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Create New Project/i })[0]).toBeInTheDocument();
    // The dashboard shows its own honest engine audit instead of the settings card.
    expect(screen.getByText(/Local engine status/i)).toBeInTheDocument();
    expect(screen.getByTestId("engine-status-strip")).toBeInTheDocument();
  });

  it("shows the capability audit on the settings tab", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "getHealth").mockResolvedValue(mockHealthData);
    vi.spyOn(api, "getCapabilities").mockResolvedValue(mockCapabilitiesData);
    vi.spyOn(api, "getProjects").mockResolvedValue([]);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/No projects yet/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /Settings & Engine/i }));

    await waitFor(() => {
      expect(screen.getByText(/System Runtime & Media Capabilities/i)).toBeInTheDocument();
    });
  });

  it("renders error message and retry button when backend connection fails", async () => {
    vi.spyOn(api, "getHealth").mockRejectedValue(new Error("Connection refused"));
    vi.spyOn(api, "getCapabilities").mockRejectedValue(new Error("Connection refused"));
    vi.spyOn(api, "getProjects").mockRejectedValue(new Error("Connection refused"));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/Backend Connection Offline/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/Retry Connection/i)).toBeInTheDocument();
  });

  it("allows opening create project modal, submitting, and navigating to project details", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "getHealth").mockResolvedValue(mockHealthData);
    vi.spyOn(api, "getCapabilities").mockResolvedValue(mockCapabilitiesData);
    vi.spyOn(api, "getProjects").mockResolvedValue([]);

    const createdProject: Project = {
      id: "proj_new_123",
      name: "New Episode #42",
      created_at: "2026-10-18T05:00:00Z",
      updated_at: "2026-10-18T05:00:00Z",
      media_count: 0,
      media_assets: [],
    };
    vi.spyOn(api, "createProject").mockResolvedValue(createdProject);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/No projects yet/i)).toBeInTheDocument();
    });

    // Click Create New Project button
    const createBtn = screen.getAllByRole("button", { name: /Create New Project/i })[0];
    await user.click(createBtn);

    // Modal opens
    expect(screen.getByLabelText(/Project Name/i)).toBeInTheDocument();
    const input = screen.getByLabelText(/Project Name/i);
    await user.type(input, "New Episode #42");

    const submitBtn = screen.getByRole("button", { name: /^Create Project$/i });
    await user.click(submitBtn);

    // Navigates to project detail view with media uploader
    await waitFor(() => {
      expect(screen.getByText("New Episode #42")).toBeInTheDocument();
    });
    expect(screen.getByText(/Import Your Video/i)).toBeInTheDocument();
    expect(screen.getByText(/Drop your long-form video here/i)).toBeInTheDocument();
  });

  it("shows recent workspaces on the dashboard and opens the studio for one of them", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "getHealth").mockResolvedValue(mockHealthData);
    vi.spyOn(api, "getCapabilities").mockResolvedValue(mockCapabilitiesData);
    vi.spyOn(api, "getProjects").mockResolvedValue([mockProjectWithMedia]);
    vi.spyOn(api, "listProjectJobs").mockResolvedValue([]);
    vi.spyOn(api, "listMediaTranscripts").mockResolvedValue([]);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/Continue where you left off/i)).toBeInTheDocument();
    });

    expect(screen.getByText("Arabic Tech Podcast #01")).toBeInTheDocument();

    // Click to open project
    const projectCard = screen.getByText("Arabic Tech Podcast #01");
    await user.click(projectCard);

    // Shows probed media details in project view
    await waitFor(() => {
      expect(screen.getByText(/FFprobe Verified/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/1920 × 1080/i)).toBeInTheDocument();
    expect(screen.getByText(/H264/i)).toBeInTheDocument();
    expect(screen.getByText(/AAC/i)).toBeInTheDocument();

    // Back button returns to the dashboard the project was opened from
    const backBtn = screen.getByRole("button", { name: /Back to projects/i });
    await user.click(backBtn);

    await waitFor(() => {
      expect(screen.getByText(/Continue where you left off/i)).toBeInTheDocument();
    });
  });

  it("lists every workspace in the My Projects library and returns there after opening one", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "getHealth").mockResolvedValue(mockHealthData);
    vi.spyOn(api, "getCapabilities").mockResolvedValue(mockCapabilitiesData);
    vi.spyOn(api, "getProjects").mockResolvedValue([mockProjectWithMedia]);
    vi.spyOn(api, "listProjectJobs").mockResolvedValue([]);
    vi.spyOn(api, "listMediaTranscripts").mockResolvedValue([]);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Arabic Tech Podcast #01")).toBeInTheDocument();
    });

    // Open the full library from the dashboard
    await user.click(screen.getByTestId("dashboard-view-all-projects"));

    await waitFor(() => {
      expect(screen.getByText(/Your Projects/i)).toBeInTheDocument();
    });
    expect(screen.getByText("podcast_full.mp4")).toBeInTheDocument();

    await user.click(screen.getByText("Arabic Tech Podcast #01"));

    await waitFor(() => {
      expect(screen.getByText(/FFprobe Verified/i)).toBeInTheDocument();
    });

    // Going back returns to the library the project was opened from
    await user.click(screen.getByRole("button", { name: /Back to projects/i }));

    await waitFor(() => {
      expect(screen.getByText(/Your Projects/i)).toBeInTheDocument();
    });
  });
});
