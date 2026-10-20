import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ProjectList } from "../features/projects/ProjectList";
import { Project } from "../types/projects";

const mockProjects: Project[] = [
  {
    id: "proj_01",
    name: "Arabic Tech Podcast #01",
    created_at: "2026-10-18T10:00:00Z",
    updated_at: "2026-10-18T10:00:00Z",
    media_count: 1,
    media_assets: [
      {
        id: "med_01",
        project_id: "proj_01",
        original_name: "episode_full.mp4",
        size_bytes: 52428800, // 50 MB
        duration_ms: 180000, // 3 mins
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
  {
    id: "proj_03",
    name: "Gaming Highlights",
    created_at: "2026-10-16T10:00:00Z",
    updated_at: "2026-10-16T10:00:00Z",
    media_count: 1,
    media_assets: [
      {
        id: "med_03",
        project_id: "proj_03",
        original_name: "gameplay.mov",
        size_bytes: 104857600, // 100 MB
        duration_ms: 360000, // 6 mins
        width: 1920,
        height: 1080,
        video_codec: "hevc",
        audio_codec: "aac",
        status: "ready",
        created_at: "2026-10-16T10:00:00Z",
      },
    ],
  },
];

describe("ProjectList Component", () => {
  const onSelectProject = vi.fn();
  const onOpenCreateModal = vi.fn();
  const onDeleteProject = vi.fn().mockResolvedValue(undefined);
  const onRenameProject = vi.fn().mockResolvedValue(undefined);
  const onDuplicateProject = vi.fn().mockResolvedValue(undefined);

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders projects in grid view with correct media badges and stats", () => {
    render(
      <ProjectList
        projects={mockProjects}
        onSelectProject={onSelectProject}
        onOpenCreateModal={onOpenCreateModal}
        onDeleteProject={onDeleteProject}
        onRenameProject={onRenameProject}
        onDuplicateProject={onDuplicateProject}
      />,
    );

    expect(screen.getByText("Your Projects")).toBeInTheDocument();
    expect(screen.getByText("Arabic Tech Podcast #01")).toBeInTheDocument();
    expect(screen.getByText("AI Coding Stream")).toBeInTheDocument();
    expect(screen.getByText("Gaming Highlights")).toBeInTheDocument();

    // Check media file details
    expect(screen.getByText("episode_full.mp4")).toBeInTheDocument();
    expect(screen.getByText("gameplay.mov")).toBeInTheDocument();
    expect(screen.getByText(/No media imported yet/i)).toBeInTheDocument();
  });

  it("filters projects by status: With Video vs Drafts", async () => {
    const user = userEvent.setup();
    render(
      <ProjectList
        projects={mockProjects}
        onSelectProject={onSelectProject}
        onOpenCreateModal={onOpenCreateModal}
        onDeleteProject={onDeleteProject}
      />,
    );

    // Click "With Video" filter
    const withVideoBtn = screen.getByRole("button", { name: /With Video \(2\)/i });
    await user.click(withVideoBtn);

    expect(screen.getByText("Arabic Tech Podcast #01")).toBeInTheDocument();
    expect(screen.getByText("Gaming Highlights")).toBeInTheDocument();
    expect(screen.queryByText("AI Coding Stream")).not.toBeInTheDocument();

    // Click "Drafts" filter
    const draftsBtn = screen.getByRole("button", { name: /Drafts \(1\)/i });
    await user.click(draftsBtn);

    expect(screen.queryByText("Arabic Tech Podcast #01")).not.toBeInTheDocument();
    expect(screen.queryByText("Gaming Highlights")).not.toBeInTheDocument();
    expect(screen.getByText("AI Coding Stream")).toBeInTheDocument();
  });

  it("switches to table view mode and displays structured tabular data", async () => {
    const user = userEvent.setup();
    render(
      <ProjectList
        projects={mockProjects}
        onSelectProject={onSelectProject}
        onOpenCreateModal={onOpenCreateModal}
        onDeleteProject={onDeleteProject}
      />,
    );

    const tableModeBtn = screen.getByRole("button", { name: /Table List View/i });
    await user.click(tableModeBtn);

    // Table headers exist
    expect(screen.getByText("Project Name")).toBeInTheDocument();
    expect(screen.getByText("Video Asset")).toBeInTheDocument();
    expect(screen.getByText("Duration")).toBeInTheDocument();
    expect(screen.getByText("Resolution")).toBeInTheDocument();
    expect(screen.getByText("Size")).toBeInTheDocument();

    // Rows render
    expect(screen.getByText("episode_full.mp4")).toBeInTheDocument();
    expect(screen.getByText("gameplay.mov")).toBeInTheDocument();
  });

  it("searches and filters projects dynamically by query", async () => {
    const user = userEvent.setup();
    render(
      <ProjectList
        projects={mockProjects}
        onSelectProject={onSelectProject}
        onOpenCreateModal={onOpenCreateModal}
        onDeleteProject={onDeleteProject}
      />,
    );

    const searchInput = screen.getByPlaceholderText(/Search projects, files.../i);
    await user.type(searchInput, "Gaming");

    expect(screen.getByText("Gaming Highlights")).toBeInTheDocument();
    expect(screen.queryByText("Arabic Tech Podcast #01")).not.toBeInTheDocument();
    expect(screen.queryByText("AI Coding Stream")).not.toBeInTheDocument();
  });

  it("handles inline project renaming smoothly", async () => {
    const user = userEvent.setup();
    render(
      <ProjectList
        projects={mockProjects}
        onSelectProject={onSelectProject}
        onOpenCreateModal={onOpenCreateModal}
        onDeleteProject={onDeleteProject}
        onRenameProject={onRenameProject}
      />,
    );

    const renameBtn = screen.getByLabelText("Rename project Arabic Tech Podcast #01");
    await user.click(renameBtn);

    // Input appears
    const input = screen.getByDisplayValue("Arabic Tech Podcast #01");
    expect(input).toBeInTheDocument();

    await user.clear(input);
    await user.type(input, "Arabic Tech Podcast Season 2");

    const saveBtn = screen.getByTitle("Save Name");
    await user.click(saveBtn);

    expect(onRenameProject).toHaveBeenCalledWith("proj_01", "Arabic Tech Podcast Season 2");
  });

  it("triggers duplicate project callback", async () => {
    const user = userEvent.setup();
    render(
      <ProjectList
        projects={mockProjects}
        onSelectProject={onSelectProject}
        onOpenCreateModal={onOpenCreateModal}
        onDeleteProject={onDeleteProject}
        onDuplicateProject={onDuplicateProject}
      />,
    );

    const duplicateBtn = screen.getByLabelText("Duplicate project Arabic Tech Podcast #01");
    await user.click(duplicateBtn);

    expect(onDuplicateProject).toHaveBeenCalledWith("proj_01");
  });

  it("opens project metadata info modal", async () => {
    const user = userEvent.setup();
    render(
      <ProjectList
        projects={mockProjects}
        onSelectProject={onSelectProject}
        onOpenCreateModal={onOpenCreateModal}
        onDeleteProject={onDeleteProject}
      />,
    );

    const infoBtn = screen.getByLabelText("Project info for Arabic Tech Podcast #01");
    await user.click(infoBtn);

    expect(screen.getByText("Primary Media Specification")).toBeInTheDocument();
    expect(screen.getByText(/ID: proj_01/i)).toBeInTheDocument();
    expect(screen.getByText("Close")).toBeInTheDocument();

    // Close modal
    await user.click(screen.getByText("Close"));
    await waitFor(() => {
      expect(screen.queryByText("Primary Media Specification")).not.toBeInTheDocument();
    });
  });

  it("renders dedicated My Projects header for the project library", () => {
    render(
      <ProjectList
        projects={mockProjects}
        onSelectProject={onSelectProject}
        onOpenCreateModal={onOpenCreateModal}
        onDeleteProject={onDeleteProject}
      />,
    );

    expect(screen.getByRole("heading", { name: "My Projects", level: 1 })).toBeInTheDocument();
    expect(screen.getByText(/3 Workspaces/i)).toBeInTheDocument();
    expect(screen.getByText(/2 videos/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Create New Project/i })).toBeInTheDocument();
  });
});
