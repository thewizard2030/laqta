import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StudioLayout } from "../components/studio/StudioLayout";
import { StudioSidebar } from "../components/studio/StudioSidebar";
import { StudioTopHeader } from "../components/studio/StudioTopHeader";
import { StudioStatusBar } from "../components/studio/StudioStatusBar";
import { CapabilitiesResponse } from "../types/capabilities";
import { HealthResponse } from "../types/health";

const mockCapabilities: CapabilitiesResponse = {
  app_name: "Laqta",
  version: "0.1.0",
  local_only: true,
  ffmpeg: {
    available: true,
    path: "/usr/bin/ffmpeg",
    version: "ffmpeg 7.1.1",
    has_libass: true,
    details: "Ready",
  },
  ffprobe: {
    available: true,
    path: "/usr/bin/ffprobe",
    version: "ffprobe 7.1.1",
    details: "Ready",
  },
  asr: { faster_whisper: false, whisperx: false },
  llm: { openai_compatible: true },
  hardware: { device: "cpu", cuda_available: false, recommended_worker_concurrency: 1 },
  storage: { data_dir: "/tmp/qatta", exists: true, writable: true },
  url_ingestion: {
    enabled: false,
    feature_flag: false,
    yt_dlp: { available: false, path: null, version: null, details: "not installed" },
    notice: "URL ingestion is disabled pending PRD FR-12 review.",
  },
};

const mockHealth: HealthResponse = {
  status: "healthy",
  app: "Laqta",
  version: "0.1.0",
  timestamp: "2026-10-18T05:00:00Z",
};

describe("Studio Layout & Navigation Components", () => {
  it("renders full studio layout with sidebar, header, main body, and status bar", () => {
    render(
      <StudioLayout
        activeTab="dashboard"
        onTabChange={vi.fn()}
        onCreateProject={vi.fn()}
        projectCount={3}
        capabilities={mockCapabilities}
        health={mockHealth}
      >
        <div data-testid="test-child-content">Workspace Content</div>
      </StudioLayout>,
    );

    expect(screen.getByTestId("studio-layout")).toBeInTheDocument();
    expect(screen.getByTestId("studio-sidebar")).toBeInTheDocument();
    expect(screen.getByTestId("studio-top-header")).toBeInTheDocument();
    expect(screen.getByTestId("studio-status-bar")).toBeInTheDocument();
    expect(screen.getByTestId("test-child-content")).toBeInTheDocument();
  });

  it("handles sidebar navigation tab switching and project creation callback", async () => {
    const user = userEvent.setup();
    const onTabChange = vi.fn();
    const onCreateProject = vi.fn();

    render(
      <StudioSidebar
        activeTab="dashboard"
        onTabChange={onTabChange}
        onCreateProject={onCreateProject}
        projectCount={5}
        capabilities={mockCapabilities}
      />,
    );

    // Switch to projects tab
    const projectsTab = screen.getByRole("button", { name: /My Projects/i });
    await user.click(projectsTab);
    expect(onTabChange).toHaveBeenCalledWith("projects");

    // Switch to settings tab
    const settingsTab = screen.getByRole("button", { name: /Settings & Engine/i });
    await user.click(settingsTab);
    expect(onTabChange).toHaveBeenCalledWith("settings");

    // Click New Project button
    const newProjectBtn = screen.getByRole("button", { name: /New Project/i });
    await user.click(newProjectBtn);
    expect(onCreateProject).toHaveBeenCalledTimes(1);
  });

  it("updates search input and handles breadcrumb clear in top header", async () => {
    const user = userEvent.setup();
    const onSearchChange = vi.fn();
    const onClearProject = vi.fn();

    render(
      <StudioTopHeader
        searchQuery=""
        onSearchChange={onSearchChange}
        capabilities={mockCapabilities}
        health={mockHealth}
        selectedProjectName="Episode 42"
        onClearSelectedProject={onClearProject}
      />,
    );

    expect(screen.getByText(/Project: Episode 42/i)).toBeInTheDocument();

    const searchInput = screen.getByTestId("studio-search-input");
    await user.type(searchInput, "hook");
    expect(onSearchChange).toHaveBeenCalled();

    const breadcrumbBack = screen.getByRole("button", { name: /Projects/i });
    await user.click(breadcrumbBack);
    expect(onClearProject).toHaveBeenCalledTimes(1);
  });

  it("displays pipeline milestones and motto in status bar", () => {
    const { rerender } = render(
      <StudioStatusBar hasMedia={false} hasTranscript={false} clipCount={0} />,
    );

    expect(screen.getByText(/No video loaded/i)).toBeInTheDocument();
    expect(screen.getByText(/Awaiting transcription/i)).toBeInTheDocument();
    expect(screen.getByText(/0 clips generated/i)).toBeInTheDocument();
    expect(screen.getByText(/Better Clips. Bigger Stories./i)).toBeInTheDocument();

    rerender(
      <StudioStatusBar
        hasMedia={true}
        mediaDetails="1080p H264"
        hasTranscript={true}
        clipCount={5}
      />,
    );

    expect(screen.getByText(/Video loaded/i)).toBeInTheDocument();
    expect(screen.getByText(/Transcription completed/i)).toBeInTheDocument();
    expect(screen.getByText(/5 clips generated/i)).toBeInTheDocument();
  });
});
