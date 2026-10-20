/**
 * Behavioral coverage for the gated YouTube import flow (PRD FR-12):
 * - With url_ingestion disabled the button is inert and explains why.
 * - With the capability enabled, the button opens a modal that requires an
 *   explicit rights confirmation before the request can even be sent.
 * - A successful POST queues the job and notifies the user (honest copy).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ProjectDetailView } from "../features/projects/ProjectDetailView";
import { api, ApiClientError } from "../lib/api/client";
import { CapabilitiesResponse } from "../types/capabilities";
import { Project } from "../types/projects";

const mockProject: Project = {
  id: "proj_1",
  name: "Test Project",
  created_at: "2026-10-18T04:00:00Z",
  updated_at: "2026-10-18T04:00:00Z",
  media_count: 0,
  media_assets: [],
} as unknown as Project;

const baseCapabilities = {
  app_name: "Laqta",
  version: "0.1.0",
  local_only: true,
  ffmpeg: {
    available: true,
    path: "/usr/bin/ffmpeg",
    version: "7",
    has_libass: true,
    details: null,
  },
  ffprobe: { available: true, path: "/usr/bin/ffprobe", version: "7", details: null },
  asr: { faster_whisper: true, whisperx: false },
  llm: { openai_compatible: false },
  hardware: { device: "cpu", cuda_available: false, recommended_worker_concurrency: 1 },
  storage: { data_dir: "/tmp/qatta", exists: true, writable: true },
} satisfies Omit<CapabilitiesResponse, "url_ingestion">;

function capabilities(urlEnabled: boolean): CapabilitiesResponse {
  return {
    ...baseCapabilities,
    url_ingestion: {
      enabled: urlEnabled,
      feature_flag: urlEnabled,
      yt_dlp: {
        available: urlEnabled,
        path: urlEnabled ? "/usr/bin/yt-dlp" : null,
        version: urlEnabled ? "2026.01.05" : null,
        details: null,
      },
      notice: urlEnabled ? null : "disabled pending FR-12 review",
    },
  };
}

describe("Gated YouTube import (FR-12)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, "listProjectJobs").mockResolvedValue([]);
    vi.spyOn(api, "listMediaTranscripts").mockResolvedValue([]);
    vi.spyOn(api, "listMediaCandidates").mockResolvedValue([]);
  });

  it("keeps the button disabled with an honest reason when capability is off", async () => {
    render(
      <ProjectDetailView
        project={mockProject}
        onBack={vi.fn()}
        onDeleteProject={vi.fn()}
        onMediaUpdated={vi.fn()}
        capabilities={capabilities(false)}
      />,
    );

    await waitFor(() => {
      const button = screen.getByRole("button", { name: /YouTube Link/i });
      expect(button).toBeDisabled();
      expect(button.title).toContain("QATTA_ENABLE_URL_INGESTION");
    });
    // And no modal exists to bypass the gate.
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("opens the modal and requires rights confirmation before submit", async () => {
    const user = userEvent.setup();
    const ingestSpy = vi
      .spyOn(api, "ingestMediaFromUrl")
      .mockResolvedValue({ job_id: "job_ing1", status: "queued", url_host: "www.youtube.com" });

    render(
      <ProjectDetailView
        project={mockProject}
        onBack={vi.fn()}
        onDeleteProject={vi.fn()}
        onMediaUpdated={vi.fn()}
        capabilities={capabilities(true)}
      />,
    );

    await user.click(await screen.findByRole("button", { name: /YouTube Link/i }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toBeInTheDocument();

    // Submit is blocked until a URL and the explicit rights checkbox exist.
    await user.click(screen.getByRole("button", { name: /Start Import/i }));
    expect(ingestSpy).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText(/Video URL/i), "https://www.youtube.com/watch?v=abc");
    await user.click(screen.getByRole("checkbox", { name: /I confirm that I own/i }));
    await user.click(screen.getByRole("button", { name: /Start Import/i }));

    await waitFor(() => {
      expect(ingestSpy).toHaveBeenCalledWith("proj_1", "https://www.youtube.com/watch?v=abc", true);
    });

    // Modal closes and honest queue toast appears.
    expect(await screen.findByText(/Import job queued/i)).toBeInTheDocument();
  });

  it("surfaces backend refusal detail inside the modal", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "ingestMediaFromUrl").mockRejectedValue(
      new ApiClientError(
        "URL ingestion is disabled pending PRD FR-12 platform-policy/rights review.",
        403,
      ),
    );

    render(
      <ProjectDetailView
        project={mockProject}
        onBack={vi.fn()}
        onDeleteProject={vi.fn()}
        onMediaUpdated={vi.fn()}
        capabilities={capabilities(true)}
      />,
    );

    await user.click(await screen.findByRole("button", { name: /YouTube Link/i }));
    await user.type(
      await screen.findByLabelText(/Video URL/i),
      "https://www.youtube.com/watch?v=abc",
    );
    await user.click(screen.getByRole("checkbox", { name: /I confirm that I own/i }));
    await user.click(screen.getByRole("button", { name: /Start Import/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/platform-policy\/rights review/i);
  });
});
