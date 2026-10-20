import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ProjectDetailView } from "../features/projects/ProjectDetailView";
import { api } from "../lib/api/client";
import { Project } from "../types/projects";
import { JobResponse } from "../types/jobs";

const mockProject: Project = {
  id: "proj_test_101",
  name: "Job Testing Project",
  created_at: "2026-10-18T05:00:00Z",
  updated_at: "2026-10-18T05:00:00Z",
  media_count: 1,
  media_assets: [
    {
      id: "med_video_01",
      project_id: "proj_test_101",
      original_name: "lecture_clip.mp4",
      size_bytes: 5242880,
      duration_ms: 60000,
      width: 1920,
      height: 1080,
      video_codec: "h264",
      audio_codec: "aac",
      status: "ready",
      created_at: "2026-10-18T05:00:00Z",
    },
  ],
};

const mockRunningJob: JobResponse = {
  id: "job_extract_01",
  project_id: "proj_test_101",
  media_id: "med_video_01",
  type: "audio_extraction",
  status: "running",
  stage: "extracting_audio",
  progress: 50.0,
  error_code: null,
  error_message: null,
  config_json: null,
  created_at: "2026-10-18T05:00:00Z",
  started_at: "2026-10-18T05:00:01Z",
  finished_at: null,
};

const mockInterruptedJob: JobResponse = {
  id: "job_interrupted_02",
  project_id: "proj_test_101",
  media_id: "med_video_01",
  type: "audio_extraction",
  status: "failed",
  stage: "failed",
  progress: 25.0,
  error_code: "INTERRUPTED_ON_RESTART",
  error_message: "Job was interrupted by server shutdown/restart. It can be safely retried.",
  config_json: null,
  created_at: "2026-10-18T04:00:00Z",
  started_at: "2026-10-18T04:00:01Z",
  finished_at: "2026-10-18T05:00:00Z",
};

describe("ProjectDetailView - Jobs & Audio Extraction", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, "listMediaTranscripts").mockResolvedValue([]);
  });

  it("renders existing jobs, displays progress, and allows starting new extraction", async () => {
    const user = userEvent.setup();
    const mockSucceededJob: JobResponse = {
      ...mockRunningJob,
      status: "succeeded",
      stage: "completed",
      progress: 100.0,
    };
    vi.spyOn(api, "listProjectJobs").mockResolvedValue([mockSucceededJob]);

    const createdJob: JobResponse = {
      ...mockRunningJob,
      id: "job_new_02",
      status: "queued",
      stage: "queued",
      progress: 0.0,
    };
    vi.spyOn(api, "createAudioExtractionJob").mockResolvedValue(createdJob);

    render(
      <ProjectDetailView
        project={mockProject}
        onBack={vi.fn()}
        onDeleteProject={vi.fn()}
        onMediaUpdated={vi.fn()}
      />,
    );

    // Initial render displays existing job
    await waitFor(() => {
      expect(screen.getByText("Processing Jobs")).toBeInTheDocument();
      expect(screen.getByText("job_extract_01")).toBeInTheDocument();
      expect(screen.getByText("Succeeded")).toBeInTheDocument();
      expect(screen.getByText("100%")).toBeInTheDocument();
    });

    // Extract Audio button
    const extractBtn = screen.getByRole("button", { name: /Extract Audio \(16 kHz\)/i });
    expect(extractBtn).toBeInTheDocument();
    await user.click(extractBtn);
    expect(api.createAudioExtractionJob).toHaveBeenCalledWith("med_video_01");
  });

  it("renders each job as a dense row with the stage and percentage inline", async () => {
    vi.spyOn(api, "listProjectJobs").mockResolvedValue([mockRunningJob]);

    render(
      <ProjectDetailView
        project={mockProject}
        onBack={vi.fn()}
        onDeleteProject={vi.fn()}
        onMediaUpdated={vi.fn()}
      />,
    );

    const row = await screen.findByTestId("job-row-job_extract_01");
    // One compact row: status chip, type, id, an inline progress bar, the
    // percentage and the stage — no stacked 140px card.
    expect(row).toHaveTextContent("audio_extraction");
    expect(row).toHaveTextContent("50%");
    expect(row).toHaveTextContent("extracting_audio");
    expect(row.className).toContain("px-3");
  });

  it("allows cancelling a running job", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "listProjectJobs").mockResolvedValue([mockRunningJob]);

    const cancelledJob: JobResponse = {
      ...mockRunningJob,
      status: "cancelled",
      stage: "cancelled",
      finished_at: "2026-10-18T05:00:05Z",
    };
    const cancelSpy = vi.spyOn(api, "cancelJob").mockResolvedValue(cancelledJob);

    render(
      <ProjectDetailView
        project={mockProject}
        onBack={vi.fn()}
        onDeleteProject={vi.fn()}
        onMediaUpdated={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("job_extract_01")).toBeInTheDocument();
    });

    const cancelBtn = screen.getByRole("button", { name: /Cancel/i });
    await user.click(cancelBtn);

    expect(cancelSpy).toHaveBeenCalledWith("job_extract_01");
    await waitFor(() => {
      expect(screen.getByText("Cancelled")).toBeInTheDocument();
    });
  });

  it("accurately renders INTERRUPTED_ON_RESTART diagnostic notice", async () => {
    vi.spyOn(api, "listProjectJobs").mockResolvedValue([mockInterruptedJob]);

    render(
      <ProjectDetailView
        project={mockProject}
        onBack={vi.fn()}
        onDeleteProject={vi.fn()}
        onMediaUpdated={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(/Error \[INTERRUPTED_ON_RESTART\]/i)).toBeInTheDocument();
      expect(screen.getByText(/safely interrupted when the server restarted/i)).toBeInTheDocument();
    });
  });
});
