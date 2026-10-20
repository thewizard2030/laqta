import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { ApiClient, ApiClientError } from "../lib/api/client";

describe("ApiClient", () => {
  let client: ApiClient;

  beforeEach(() => {
    client = new ApiClient({ baseUrl: "http://127.0.0.1:8000" });
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("fetches health status successfully", async () => {
    const mockHealth = {
      status: "healthy",
      app: "Laqta",
      version: "0.1.0",
      timestamp: "2026-10-18T05:00:00Z",
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockHealth,
    });

    const result = await client.getHealth();
    expect(result).toEqual(mockHealth);
  });

  it("fetches system capabilities successfully", async () => {
    const mockCapabilities = {
      app_name: "Laqta",
      version: "0.1.0",
      local_only: true,
      ffmpeg: {
        available: true,
        path: "/usr/bin/ffmpeg",
        version: "ffmpeg version 7.1.1",
        has_libass: true,
        details: "FFmpeg detected",
      },
      ffprobe: {
        available: true,
        path: "/usr/bin/ffprobe",
        version: "ffprobe version 7.1.1",
        details: "FFprobe detected",
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
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockCapabilities,
    });

    const result = await client.getCapabilities();
    expect(result).toEqual(mockCapabilities);
  });

  it("creates and lists projects successfully", async () => {
    const mockProject = {
      id: "proj_123",
      name: "Podcast Ep 1",
      created_at: "2026-10-18T05:00:00Z",
      updated_at: "2026-10-18T05:00:00Z",
      media_count: 0,
      media_assets: [],
    };

    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockProject,
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [mockProject],
      });

    const created = await client.createProject("Podcast Ep 1");
    expect(created.id).toBe("proj_123");

    const list = await client.getProjects();
    expect(list).toHaveLength(1);
    expect(list[0].name).toBe("Podcast Ep 1");
  });

  it("deletes project successfully", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
    });

    await expect(client.deleteProject("proj_123")).resolves.toBeUndefined();
  });

  it("throws ApiClientError on HTTP error status with server message", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      statusText: "Bad Request",
      json: async () => ({ detail: "Unsupported file extension '.exe'" }),
    });

    await expect(client.createProject("")).rejects.toThrow(ApiClientError);
    await expect(client.createProject("")).rejects.toThrow("Unsupported file extension '.exe'");
  });

  it("creates, polls, and cancels background jobs via API client", async () => {
    const mockJob = {
      id: "job_123",
      project_id: "proj_123",
      media_id: "med_123",
      type: "audio_extraction",
      status: "queued" as const,
      stage: "queued",
      progress: 0.0,
      error_code: null,
      error_message: null,
      config_json: null,
      created_at: "2026-10-18T05:00:00Z",
      started_at: null,
      finished_at: null,
    };

    const mockRunningJob = {
      ...mockJob,
      status: "running" as const,
      progress: 45.0,
      stage: "extracting_audio",
    };
    const mockCancelledJob = { ...mockJob, status: "cancelled" as const, stage: "cancelled" };

    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => mockJob })
      .mockResolvedValueOnce({ ok: true, json: async () => mockRunningJob })
      .mockResolvedValueOnce({ ok: true, json: async () => mockCancelledJob })
      .mockResolvedValueOnce({ ok: true, json: async () => [mockCancelledJob] });

    const created = await client.createAudioExtractionJob("med_123");
    expect(created.id).toBe("job_123");
    expect(created.status).toBe("queued");

    const polled = await client.getJob("job_123");
    expect(polled.status).toBe("running");
    expect(polled.progress).toBe(45.0);

    const cancelled = await client.cancelJob("job_123");
    expect(cancelled.status).toBe("cancelled");

    const projectJobs = await client.listProjectJobs("proj_123");
    expect(projectJobs).toHaveLength(1);
    expect(projectJobs[0].id).toBe("job_123");
  });

  it("updates project name and duplicates project successfully", async () => {
    const mockUpdatedProject = {
      id: "proj_123",
      name: "Renamed Project",
      created_at: "2026-10-18T05:00:00Z",
      updated_at: "2026-10-18T06:00:00Z",
      media_count: 0,
      media_assets: [],
    };

    const mockDuplicateProject = {
      id: "proj_456",
      name: "Renamed Project (Copy)",
      created_at: "2026-10-18T06:05:00Z",
      updated_at: "2026-10-18T06:05:00Z",
      media_count: 0,
      media_assets: [],
    };

    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => mockUpdatedProject })
      .mockResolvedValueOnce({ ok: true, json: async () => mockDuplicateProject });

    const updated = await client.updateProject("proj_123", "Renamed Project");
    expect(updated.name).toBe("Renamed Project");

    const duplicated = await client.duplicateProject("proj_123");
    expect(duplicated.id).toBe("proj_456");
    expect(duplicated.name).toBe("Renamed Project (Copy)");
  });

  it("handles pipeline, manifest, utterances, render, and caption API calls", async () => {
    const mockPipelineJob = {
      id: "job_pipe_1",
      project_id: "proj_123",
      media_id: null,
      type: "pipeline",
      status: "queued" as const,
      stage: "queued",
      progress: 0.0,
      error_code: null,
      error_message: null,
      config_json: null,
      created_at: "2026-10-18T05:00:00Z",
      started_at: null,
      finished_at: null,
    };

    const mockManifest = { project_id: "proj_123", duration_sec: 120.0 };
    const mockUtterances = [{ u_id: "U_0001", text: "Hello world", start_ms: 0, end_ms: 1500 }];
    const mockRenderJob = { ...mockPipelineJob, id: "job_render_1", type: "render" };
    const mockCaptions = {
      candidate_id: "cand_1",
      media_id: "med_1",
      transcript_id: "tr_1",
      timing_granularity: "word" as const,
      karaoke_used: true,
      warnings: [],
      style: {},
      created_at: "2026-10-18T05:00:00Z",
    };
    const mockArtifacts = {
      candidate_id: "cand_1",
      media_id: "med_1",
      captions: [],
      rendered_clips: [],
      warnings: [],
    };

    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => mockPipelineJob })
      .mockResolvedValueOnce({ ok: true, json: async () => mockManifest })
      .mockResolvedValueOnce({ ok: true, json: async () => mockUtterances })
      .mockResolvedValueOnce({ ok: true, json: async () => mockRenderJob })
      .mockResolvedValueOnce({ ok: true, json: async () => mockCaptions })
      .mockResolvedValueOnce({ ok: true, json: async () => mockArtifacts });

    const pipeJob = await client.createPipelineJob("proj_123", { stages: ["s00", "s01"] });
    expect(pipeJob.id).toBe("job_pipe_1");

    const manifest = await client.getProjectManifest("proj_123");
    expect(manifest.project_id).toBe("proj_123");

    const utterances = await client.getProjectUtterances("proj_123");
    expect(utterances).toHaveLength(1);
    expect(utterances[0].u_id).toBe("U_0001");

    const renderJob = await client.createRenderJob("cand_1", { layout: "center_crop" });
    expect(renderJob.id).toBe("job_render_1");

    const captions = await client.createCandidateCaptions("cand_1");
    expect(captions.timing_granularity).toBe("word");

    const artifacts = await client.getCandidateArtifacts("cand_1");
    expect(artifacts.candidate_id).toBe("cand_1");

    expect(client.getRenderedVideoUrl("cand_1")).toContain("/api/candidates/cand_1/rendered-video");
    expect(client.getRenderFileUrl("rnd_1")).toContain("/api/renders/rnd_1/file");
  });
});
