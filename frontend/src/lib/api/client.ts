/**
 * Typed API client for the Laqta backend.
 * Local-first client connecting to 127.0.0.1 by default.
 */

import { CapabilitiesResponse } from "../../types/capabilities";
import { HealthResponse } from "../../types/health";
import { JobResponse } from "../../types/jobs";
import { MediaAsset } from "../../types/media";
import { Project } from "../../types/projects";
import { TranscriptionRequest, TranscriptResponse } from "../../types/transcription";
import {
  Candidate,
  CandidateGenerationResponse,
  CandidateUpdateRequest,
} from "../../types/candidates";
import {
  CandidateArtifactsResponse,
  CandidateCaptionsResponse,
  CaptionGenerationRequest,
  RenderRequest,
} from "../../types/rendering";

export class ApiClientError extends Error {
  public status?: number;
  public details?: unknown;

  constructor(message: string, status?: number, details?: unknown) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.details = details;
  }
}

export interface ApiClientOptions {
  baseUrl?: string;
  timeoutMs?: number;
}

export interface RequestOptions extends RequestInit {
  timeoutMs?: number;
}

export class ApiClient {
  private baseUrl: string;
  private defaultTimeoutMs: number;

  constructor(options: ApiClientOptions = {}) {
    // In dev, Vite proxies /api to 127.0.0.1:8000; or use explicit base url
    this.baseUrl = options.baseUrl ?? "";
    this.defaultTimeoutMs = options.timeoutMs ?? 30000;
  }

  private async request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    const { timeoutMs: customTimeout, ...fetchOptions } = options;
    const timeoutMs = customTimeout ?? this.defaultTimeoutMs;
    const url = `${this.baseUrl}${endpoint}`;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const response = await fetch(url, {
        ...fetchOptions,
        signal: controller.signal,
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          ...fetchOptions.headers,
        },
      });

      if (!response.ok) {
        let errorBody: unknown;
        let errorMessage = `API request failed: ${response.status} ${response.statusText}`;
        try {
          errorBody = await response.json();
          if (typeof errorBody === "object" && errorBody !== null && "detail" in errorBody) {
            errorMessage = String((errorBody as { detail: unknown }).detail);
          }
        } catch {
          errorBody = await response.text();
          if (typeof errorBody === "string" && errorBody) {
            errorMessage = errorBody;
          }
        }
        throw new ApiClientError(errorMessage, response.status, errorBody);
      }

      if (response.status === 204) {
        return undefined as T;
      }

      return (await response.json()) as T;
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        throw err;
      }
      if (err instanceof DOMException && err.name === "AbortError") {
        throw new ApiClientError(`API request timed out after ${timeoutMs}ms`);
      }
      const message = err instanceof Error ? err.message : "Unknown network error";
      throw new ApiClientError(`Connection error: ${message}`);
    } finally {
      clearTimeout(timeoutId);
    }
  }

  /**
   * Health check endpoint: GET /api/health
   */
  async getHealth(): Promise<HealthResponse> {
    return this.request<HealthResponse>("/api/health");
  }

  /**
   * Honest capability check endpoint: GET /api/capabilities
   */
  async getCapabilities(): Promise<CapabilitiesResponse> {
    return this.request<CapabilitiesResponse>("/api/capabilities");
  }

  /**
   * List all projects: GET /api/projects
   */
  async getProjects(): Promise<Project[]> {
    return this.request<Project[]>("/api/projects");
  }

  /**
   * Create a new project: POST /api/projects
   */
  async createProject(name: string): Promise<Project> {
    return this.request<Project>("/api/projects", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
  }

  /**
   * Get project by ID: GET /api/projects/{projectId}
   */
  async getProject(projectId: string): Promise<Project> {
    return this.request<Project>(`/api/projects/${projectId}`);
  }

  /**
   * Delete project: DELETE /api/projects/{projectId}
   */
  async deleteProject(projectId: string): Promise<void> {
    await this.request<void>(`/api/projects/${projectId}`, {
      method: "DELETE",
    });
  }

  /**
   * Update project details: PATCH /api/projects/{projectId}
   */
  async updateProject(projectId: string, name: string): Promise<Project> {
    return this.request<Project>(`/api/projects/${projectId}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    });
  }

  /**
   * Duplicate project container: POST /api/projects/{projectId}/duplicate
   */
  async duplicateProject(projectId: string): Promise<Project> {
    return this.request<Project>(`/api/projects/${projectId}/duplicate`, {
      method: "POST",
    });
  }

  /**
   * Upload video file to project: POST /api/projects/{projectId}/media
   * Supports progress callbacks.
   */
  async uploadMedia(
    projectId: string,
    file: File,
    onProgress?: (percent: number) => void,
  ): Promise<MediaAsset> {
    const url = `${this.baseUrl}/api/projects/${projectId}/media`;

    return new Promise<MediaAsset>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const formData = new FormData();
      formData.append("file", file);

      if (onProgress && xhr.upload) {
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable) {
            const percent = Math.round((event.loaded / event.total) * 100);
            onProgress(percent);
          }
        };
      }

      xhr.onload = () => {
        let responseJson: unknown;
        try {
          responseJson = JSON.parse(xhr.responseText);
        } catch {
          responseJson = xhr.responseText;
        }

        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(responseJson as MediaAsset);
        } else {
          let errorDetail = `Upload failed (${xhr.status})`;
          if (
            typeof responseJson === "object" &&
            responseJson !== null &&
            "detail" in responseJson
          ) {
            errorDetail = String((responseJson as { detail: unknown }).detail);
          }
          reject(new ApiClientError(errorDetail, xhr.status, responseJson));
        }
      };

      xhr.onerror = () => {
        reject(new ApiClientError("Network error during media upload."));
      };

      xhr.ontimeout = () => {
        reject(new ApiClientError("Media upload timed out."));
      };

      xhr.open("POST", url, true);
      // Long timeout for large video uploads (5 minutes)
      xhr.timeout = 300000;
      xhr.send(formData);
    });
  }

  /**
   * Get media asset: GET /api/media/{mediaId}
   */
  async getMedia(mediaId: string): Promise<MediaAsset> {
    return this.request<MediaAsset>(`/api/media/${mediaId}`);
  }

  /**
   * Queue a gated URL ingestion job: POST /api/media/url (PRD FR-12).
   *
   * The backend is fail-closed: the request succeeds only when the operator
   * flag is enabled AND yt-dlp is installed AND rights were confirmed. Any
   * refusal raises ApiClientError with the backend's explicit detail text.
   */
  async ingestMediaFromUrl(
    projectId: string,
    url: string,
    rightsConfirmed: boolean,
  ): Promise<{ job_id: string; status: string; url_host: string }> {
    return this.request("/api/media/url", {
      method: "POST",
      body: JSON.stringify({
        project_id: projectId,
        url,
        rights_confirmed: rightsConfirmed,
      }),
    });
  }

  /**
   * Enqueue 16 kHz mono WAV audio extraction job: POST /api/media/{mediaId}/audio-extraction-jobs
   */
  async createAudioExtractionJob(mediaId: string): Promise<JobResponse> {
    return this.request<JobResponse>(`/api/media/${mediaId}/audio-extraction-jobs`, {
      method: "POST",
    });
  }

  /**
   * Create generic background job: POST /api/jobs
   */
  async createJob(payload: {
    project_id: string;
    media_id?: string;
    type?: string;
    config?: Record<string, unknown>;
  }): Promise<JobResponse> {
    return this.request<JobResponse>("/api/jobs", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  /**
   * Get job status and details: GET /api/jobs/{jobId}
   */
  async getJob(jobId: string): Promise<JobResponse> {
    return this.request<JobResponse>(`/api/jobs/${jobId}`);
  }

  /**
   * Cancel queued or running job: POST /api/jobs/{jobId}/cancel
   */
  async cancelJob(jobId: string): Promise<JobResponse> {
    return this.request<JobResponse>(`/api/jobs/${jobId}/cancel`, {
      method: "POST",
    });
  }

  /**
   * List all jobs for a project: GET /api/projects/{projectId}/jobs
   */
  async listProjectJobs(projectId: string): Promise<JobResponse[]> {
    return this.request<JobResponse[]>(`/api/projects/${projectId}/jobs`);
  }

  /**
   * Clear historical finished/failed jobs for a project: DELETE /api/projects/{projectId}/jobs
   */
  async clearProjectJobs(projectId: string): Promise<{ deleted_count: number }> {
    return this.request<{ deleted_count: number }>(`/api/projects/${projectId}/jobs`, {
      method: "DELETE",
    });
  }

  /**
   * Enqueue transcription job: POST /api/media/{mediaId}/transcription-jobs
   */
  async createTranscriptionJob(mediaId: string, req?: TranscriptionRequest): Promise<JobResponse> {
    return this.request<JobResponse>(`/api/media/${mediaId}/transcription-jobs`, {
      method: "POST",
      body: JSON.stringify(req ?? {}),
    });
  }

  /**
   * List transcripts for a media asset: GET /api/media/{mediaId}/transcripts
   */
  async listMediaTranscripts(mediaId: string): Promise<TranscriptResponse[]> {
    return this.request<TranscriptResponse[]>(`/api/media/${mediaId}/transcripts`);
  }

  /**
   * Get single transcript by ID: GET /api/transcripts/{transcriptId}
   */
  async getTranscript(transcriptId: string): Promise<TranscriptResponse> {
    return this.request<TranscriptResponse>(`/api/transcripts/${transcriptId}`);
  }

  /**
   * Generate candidates for a media asset: POST /api/media/{mediaId}/candidates
   * Deterministic baseline by default; optional LLM reranking happens
   * server-side only when it is explicitly enabled there.
   */
  async generateCandidates(
    mediaId: string,
    req?: Partial<{
      min_duration_s: number;
      max_duration_s: number;
    }>,
    timeoutMs: number = 60000,
  ): Promise<CandidateGenerationResponse> {
    return this.request<CandidateGenerationResponse>(`/api/media/${mediaId}/candidates`, {
      method: "POST",
      body: JSON.stringify(req ?? {}),
      timeoutMs,
    });
  }

  /**
   * List persisted candidates ranked by CPS: GET /api/media/{mediaId}/candidates
   */
  async listMediaCandidates(mediaId: string): Promise<Candidate[]> {
    return this.request<Candidate[]>(`/api/media/${mediaId}/candidates`);
  }

  /**
   * Update reviewed candidate boundaries/title/hook:
   * PATCH /api/candidates/{candidateId}
   */
  async updateCandidate(candidateId: string, req: CandidateUpdateRequest): Promise<Candidate> {
    return this.request<Candidate>(`/api/candidates/${candidateId}`, {
      method: "PATCH",
      body: JSON.stringify(req),
    });
  }

  /**
   * Enqueue a full or partial core pipeline job:
   * POST /api/projects/{projectId}/pipeline-jobs
   */
  async createPipelineJob(
    projectId: string,
    options: { stages?: string[]; force?: boolean } = {},
  ): Promise<JobResponse> {
    return this.request<JobResponse>(`/api/projects/${projectId}/pipeline-jobs`, {
      method: "POST",
      body: JSON.stringify(options),
    });
  }

  /**
   * Fetch canonical qatta manifest directly:
   * GET /api/projects/{projectId}/manifest
   */
  async getProjectManifest(projectId: string): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>(`/api/projects/${projectId}/manifest`);
  }

  /**
   * Fetch atomic utterances for project:
   * GET /api/projects/{projectId}/utterances
   */
  async getProjectUtterances(projectId: string): Promise<
    Array<{
      u_id: string;
      text: string;
      start_ms: number;
      end_ms: number;
      words?: Array<{ word: string; start_ms: number; end_ms: number; prob?: number }>;
    }>
  > {
    return this.request<
      Array<{
        u_id: string;
        text: string;
        start_ms: number;
        end_ms: number;
        words?: Array<{ word: string; start_ms: number; end_ms: number; prob?: number }>;
      }>
    >(`/api/projects/${projectId}/utterances`);
  }

  /**
   * Enqueue render job for a candidate:
   * POST /api/candidates/{candidateId}/render-jobs
   */
  async createRenderJob(candidateId: string, payload?: RenderRequest): Promise<JobResponse> {
    return this.request<JobResponse>(`/api/candidates/${candidateId}/render-jobs`, {
      method: "POST",
      body: JSON.stringify(payload ?? {}),
    });
  }

  /**
   * Generate editable SRT/ASS captions for a candidate:
   * POST /api/candidates/{candidateId}/captions
   */
  async createCandidateCaptions(
    candidateId: string,
    payload?: CaptionGenerationRequest,
    timeoutMs: number = 60000,
  ): Promise<CandidateCaptionsResponse> {
    return this.request<CandidateCaptionsResponse>(`/api/candidates/${candidateId}/captions`, {
      method: "POST",
      body: JSON.stringify(payload ?? {}),
      timeoutMs,
    });
  }

  /**
   * List artifacts for candidate:
   * GET /api/candidates/{candidateId}/artifacts
   */
  async getCandidateArtifacts(candidateId: string): Promise<CandidateArtifactsResponse> {
    return this.request<CandidateArtifactsResponse>(`/api/candidates/${candidateId}/artifacts`);
  }

  /**
   * Get direct download/stream URL for candidate's rendered video.
   */
  getRenderedVideoUrl(candidateId: string): string {
    return `${this.baseUrl}/api/candidates/${candidateId}/rendered-video`;
  }

  /**
   * Get direct download/stream URL for a specific render ID.
   */
  getRenderFileUrl(renderId: string): string {
    return `${this.baseUrl}/api/renders/${renderId}/file`;
  }
}

export const api = new ApiClient();
