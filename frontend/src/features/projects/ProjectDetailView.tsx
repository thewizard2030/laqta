import React, { useEffect, useRef, useState, useCallback, useMemo } from "react";
import {
  ArrowLeft,
  Film,
  Clock,
  Monitor,
  Volume2,
  FileVideo,
  CheckCircle2,
  Trash2,
  AlertCircle,
  Loader2,
  XCircle,
  Music,
  RotateCw,
  Sparkles,
  Layers,
  ChevronDown,
  ChevronUp,
  Pencil,
  Check,
  X,
  UploadCloud,
  Download,
  Calendar,
  Clapperboard,
} from "lucide-react";
import { CapabilitiesResponse } from "../../types/capabilities";
import { JobResponse, JobStatus } from "../../types/jobs";
import { MediaAsset } from "../../types/media";
import { Project } from "../../types/projects";
import { Candidate } from "../../types/candidates";
import { TranscriptionRequest, TranscriptResponse } from "../../types/transcription";
import { CandidatesPanel, TranscriptionJobState } from "../clips/CandidatesPanel";
import { api } from "../../lib/api/client";
import { generateMediaFileUrl } from "../../lib/api/mediaUrl";
import { buildCaptionStyle } from "../../lib/captions/style";
import { TranscriptViewer } from "../transcription/TranscriptViewer";
import { MediaUploader } from "./MediaUploader";
import { YouTubeImportModal } from "./YouTubeImportModal";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { Toast, ToastType } from "../../components/ui/Toast";
import {
  AspectRatioMode,
  InspectorTab,
  ClipEditSettings,
  CaptionStyleOptions,
  ExportSettings,
} from "../studio/types";
import { ShortsCanvasPlayer } from "../../components/studio/canvas/ShortsCanvasPlayer";
import { SuggestedClipsList } from "../../components/studio/clips/SuggestedClipsList";
import { MultiTrackTimeline } from "../../components/studio/timeline/MultiTrackTimeline";
import { InspectorPanel } from "../../components/studio/inspector/InspectorPanel";
import { cleanDisplayText } from "../../lib/format";
import { YouTubeIcon } from "../../components/ui/BrandIcons";

interface ProjectDetailViewProps {
  project: Project;
  onBack: () => void;
  onDeleteProject: (projectId: string) => Promise<void>;
  onRenameProject?: (projectId: string, newName: string) => Promise<void>;
  onMediaUpdated: (updatedProject: Project) => void;
  capabilities?: CapabilitiesResponse | null;
  onStatsChange?: (stats: { clipCount: number; hasTranscript: boolean }) => void;
}

/**
 * Latest transcription job state for honest empty/cancelled/failed candidate
 * states. Newest job wins (list is ordered newest-first by the backend and
 * local prepend).
 */
function latestTranscriptionJobState(jobs: JobResponse[]): TranscriptionJobState | null {
  const transcriptionJobs = jobs.filter((j) => j.type === "transcription");
  if (transcriptionJobs.length === 0) return null;
  const job = transcriptionJobs[0];
  const status: TranscriptionJobState["status"] =
    (job.status as TranscriptionJobState["status"]) ?? "succeeded";
  return { status, errorMessage: job.error_message ?? null };
}

export const ProjectDetailView: React.FC<ProjectDetailViewProps> = ({
  project,
  onBack,
  onDeleteProject,
  onRenameProject,
  onMediaUpdated,
  capabilities,
  onStatsChange,
}) => {
  const [isDeleting, setIsDeleting] = useState(false);
  const [isEditingName, setIsEditingName] = useState(false);
  const [editingName, setEditingName] = useState(project.name);
  const [isSavingName, setIsSavingName] = useState(false);
  const [showUploader, setShowUploader] = useState(false);
  const [jobs, setJobs] = useState<JobResponse[]>([]);
  const [isLoadingJobs, setIsLoadingJobs] = useState(false);
  const [isSubmittingJob, setIsSubmittingJob] = useState(false);
  const [cancellingJobId, setCancellingJobId] = useState<string | null>(null);
  const [transcripts, setTranscripts] = useState<TranscriptResponse[]>([]);
  const [isLoadingTranscripts, setIsLoadingTranscripts] = useState(false);
  const [isSubmittingTranscription, setIsSubmittingTranscription] = useState(false);
  const [localCapabilities, setLocalCapabilities] = useState<CapabilitiesResponse | null>(
    capabilities ?? null,
  );

  // Studio Workbench State
  const [studioViewMode, setStudioViewMode] = useState<"studio" | "diagnostics">("studio");
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null);
  const [isGeneratingCandidates, setIsGeneratingCandidates] = useState(false);
  const [currentTimeSec, setCurrentTimeSec] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [aspectRatio, setAspectRatio] = useState<AspectRatioMode>("9:16");
  const [showSpeakerGuide, setShowSpeakerGuide] = useState<boolean>(true);
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("edit");
  const [isBackendOffline, setIsBackendOffline] = useState<boolean>(false);
  const [isJobHistoryOpen, setIsJobHistoryOpen] = useState<boolean>(true);
  const [isClearingJobs, setIsClearingJobs] = useState<boolean>(false);
  const [isYouTubeModalOpen, setIsYouTubeModalOpen] = useState<boolean>(false);
  const [thumbnailEpoch, setThumbnailEpoch] = useState<number>(0);

  /**
   * A one-second clock for the "elapsed" column.
   *
   * The current time is **state**, not a `Date.now()` call during render:
   * reading the clock while rendering makes the output non-reproducible and
   * breaks the React purity rule. The tick only runs while a job is active.
   */
  const [nowMs, setNowMs] = useState<number>(() => Date.now());

  /** True while at least one job is queued or running. */
  const hasActiveJob = useMemo(
    () => jobs.some((j) => j.status === "queued" || j.status === "running"),
    [jobs],
  );
  // Job IDs whose succeeded url_ingestion media has already been picked up.
  const handledIngestJobIds = useRef<Set<string>>(new Set());
  const handledThumbnailJobIds = useRef<Set<string>>(new Set());

  const urlIngestion = localCapabilities?.url_ingestion ?? null;
  const urlIngestionReady = urlIngestion?.enabled === true;

  // Shared confirmation dialog (delete project / clear jobs).
  const [confirmRequest, setConfirmRequest] = useState<{
    title: string;
    message: string;
    confirmLabel: string;
    onConfirm: () => Promise<void> | void;
  } | null>(null);
  const [isConfirming, setIsConfirming] = useState(false);

  // Non-blocking feedback replacing native alert() calls.
  const [toast, setToast] = useState<{ type: ToastType; message: string } | null>(null);

  const [editSettings, setEditSettings] = useState<ClipEditSettings>({
    clipName: "Viral Hook Short",
    startSec: 0,
    endSec: 30,
    aspectRatio: "9:16",
    autoReframe: true,
    motionSmoothing: 75,
    splitScreen: false,
  });

  const [captionOptions, setCaptionOptions] = useState<CaptionStyleOptions>({
    preset: "neon-glow",
    fontFamily: "Noto Sans Arabic",
    fontSize: "lg",
    position: "bottom",
    textColor: "#FFFFFF",
    highlightColor: "#00F2FE",
    karaokeSync: true,
  });

  const [exportSettings, setExportSettings] = useState<ExportSettings>({
    fileName: `${project.name.replace(/[^a-zA-Z0-9_-]/g, "_")}_short.mp4`,
    resolution: "1080p",
    format: "mp4",
    burnInSubtitles: true,
  });

  // Mirror the prop into local state during render (React's documented
  // pattern for a prop change) and only fetch when the parent has none.
  const [previousCapabilities, setPreviousCapabilities] = useState<
    CapabilitiesResponse | null | undefined
  >(capabilities);
  if (previousCapabilities !== capabilities) {
    setPreviousCapabilities(capabilities);
    setLocalCapabilities(capabilities ?? null);
  }

  useEffect(() => {
    if (capabilities) return;
    let cancelled = false;
    api
      .getCapabilities()
      .then((detected) => {
        if (!cancelled) setLocalCapabilities(detected);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [capabilities]);

  const hasMedia = project.media_assets.length > 0;
  const primaryMedia = hasMedia ? project.media_assets[0] : null;

  const fetchTranscripts = useCallback(async (mediaId: string) => {
    try {
      const data = await api.listMediaTranscripts(mediaId);
      setTranscripts(data);
    } catch (err) {
      console.error("Failed to load transcripts:", err);
    }
  }, []);

  const fetchJobs = useCallback(async () => {
    try {
      const projectJobs = await api.listProjectJobs(project.id);
      setJobs(projectJobs);
      setIsBackendOffline(false);
    } catch (err) {
      console.error("Failed to load project jobs:", err);
      setIsBackendOffline(true);
    }
  }, [project.id]);

  useEffect(() => {
    // The loading flag is a single boolean set before the request resolves;
    // it is not the cascading-render pattern the rule guards against.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIsLoadingJobs(true);
    fetchJobs().finally(() => setIsLoadingJobs(false));
  }, [fetchJobs]);

  const primaryMediaId = primaryMedia?.id;

  useEffect(() => {
    if (primaryMediaId) {
      // One boolean flag before the request resolves — not a cascading render.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setIsLoadingTranscripts(true);
      fetchTranscripts(primaryMediaId).finally(() => setIsLoadingTranscripts(false));
    } else {
      setTranscripts([]);
    }
  }, [primaryMediaId, fetchTranscripts]);

  const fetchCandidates = useCallback(async (mediaId: string) => {
    try {
      const list = await api.listMediaCandidates(mediaId);
      setCandidates(list);
      setSelectedCandidate((prev) => {
        if (!prev && list.length > 0) {
          const firstTitle = cleanDisplayText(list[0].title);
          setEditSettings((editPrev) => ({
            ...editPrev,
            clipName: firstTitle || `Clip #${list[0].id}`,
            startSec: list[0].start_ms / 1000,
            endSec: list[0].end_ms / 1000,
          }));
          return list[0];
        }
        return prev;
      });
    } catch {
      // In case candidate generation has not run or endpoint is not mocked in tests
      setCandidates([]);
    }
  }, []);

  useEffect(() => {
    if (primaryMediaId) {
      // The candidates arrive asynchronously; the setState happens in the
      // promise callback, not synchronously in this effect body.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      fetchCandidates(primaryMediaId);
    } else {
      // No media means no candidates — reset during render so the list is
      // never rendered with a stale selection.
      setCandidates([]);
      setSelectedCandidate(null);
    }
  }, [primaryMediaId, fetchCandidates]);

  const handleSelectCandidate = (candidate: Candidate) => {
    setSelectedCandidate(candidate);
    const startSec = candidate.start_ms / 1000;
    const endSec = candidate.end_ms / 1000;
    const cleanTitle = cleanDisplayText(candidate.title);
    setCurrentTimeSec(startSec);
    setEditSettings((prev) => ({
      ...prev,
      clipName: cleanTitle || `Clip #${candidate.id}`,
      startSec,
      endSec,
    }));
    setExportSettings((prev) => ({
      ...prev,
      fileName: `${(cleanTitle || "Laqta_Short").replace(/[^a-zA-Z0-9_\u0600-\u06FF-]/g, "_")}.mp4`,
    }));
  };

  const handleGenerateCandidates = async () => {
    if (!primaryMedia) return;
    setIsGeneratingCandidates(true);
    try {
      const result = await api.generateCandidates(primaryMedia.id);
      setCandidates(result.candidates);
      if (result.candidates.length > 0) {
        handleSelectCandidate(result.candidates[0]);
      }
    } catch (err) {
      console.error("Failed to generate candidates:", err);
      try {
        const persisted = await api.listMediaCandidates(primaryMedia.id);
        if (persisted.length > 0) {
          setCandidates(persisted);
          handleSelectCandidate(persisted[0]);
          setToast({
            type: "info",
            message: `Loaded ${persisted.length} generated clip candidates.`,
          });
          return;
        }
      } catch {
        // ignore fallback error
      }
      setToast({
        type: "error",
        message: `Could not generate clips: ${err instanceof Error ? err.message : String(err)}`,
      });
    } finally {
      setIsGeneratingCandidates(false);
    }
  };

  const handleSaveName = async () => {
    const trimmed = editingName.trim();
    if (!trimmed || trimmed === project.name || !onRenameProject) {
      setIsEditingName(false);
      return;
    }
    setIsSavingName(true);
    try {
      await onRenameProject(project.id, trimmed);
      setIsEditingName(false);
    } catch (err) {
      console.error("Failed to rename project:", err);
      setToast({
        type: "error",
        message: err instanceof Error ? err.message : "Failed to rename project",
      });
    } finally {
      setIsSavingName(false);
    }
  };

  const handleUpdateEditSettings = (patch: Partial<ClipEditSettings>) => {
    setEditSettings((prev) => {
      const updated = { ...prev, ...patch };
      if (patch.aspectRatio) {
        setAspectRatio(patch.aspectRatio);
      }
      return updated;
    });
  };

  const handleUpdateCaptionOptions = (patch: Partial<CaptionStyleOptions>) => {
    setCaptionOptions((prev) => ({ ...prev, ...patch }));
  };

  const handleUpdateExportSettings = (patch: Partial<ExportSettings>) => {
    setExportSettings((prev) => ({ ...prev, ...patch }));
  };

  /**
   * Export rendering handler: Enqueues a local FFmpeg render job for the
   * active or selected clip candidate with burned-in subtitles and 9:16 crop.
   *
   * The inspector's caption settings are forwarded to the renderer, so the
   * Captions tab (font, size, position, colours, word-by-word sync) really
   * changes the burned-in subtitles.
   */
  const handleExport = async () => {
    const targetCandidate = selectedCandidate || (candidates.length > 0 ? candidates[0] : null);
    if (!targetCandidate) {
      setToast({
        type: "error",
        message: "No clip candidate available to export. Generate or select a clip first.",
      });
      return;
    }

    try {
      const job = await api.createRenderJob(targetCandidate.id, {
        layout: "center_crop",
        quality: exportSettings.resolution === "720p" ? "cpu_friendly" : "high",
        caption_format: exportSettings.burnInSubtitles ? "ass" : "none",
        style: buildCaptionStyle(captionOptions),
        overwrite: true,
      });
      setToast({
        type: "success",
        message: `Render job enqueued for "${targetCandidate.title || targetCandidate.id}" (${job.id}).`,
      });
      fetchJobs();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to enqueue render job.";
      setToast({
        type: "error",
        message: `Export failed: ${msg}`,
      });
    }
  };

  // Polling when any job is queued or running
  useEffect(() => {
    if (!hasActiveJob) return;

    const interval = setInterval(() => {
      fetchJobs();
      if (primaryMedia) {
        fetchTranscripts(primaryMedia.id);
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [hasActiveJob, fetchJobs, primaryMedia, fetchTranscripts]);

  // Surface media created by succeeded url_ingestion jobs (downloads finish
  // in the background after the dialog is already closed).
  useEffect(() => {
    const succeededIngests = jobs.filter(
      (j) =>
        j.type === "url_ingestion" &&
        j.status === "succeeded" &&
        !handledIngestJobIds.current.has(j.id),
    );
    if (succeededIngests.length === 0) return;

    succeededIngests.forEach(async (job) => {
      handledIngestJobIds.current.add(job.id);
      let mediaId: string | null = null;
      try {
        const parsed = JSON.parse(job.config_json ?? "{}") as { media_id?: string };
        mediaId = parsed.media_id ?? null;
      } catch {
        mediaId = null;
      }
      if (!mediaId || project.media_assets.some((m) => m.id === mediaId)) return;
      try {
        const media = await api.getMedia(mediaId);
        onMediaUpdated({
          ...project,
          media_count: project.media_count + 1,
          media_assets: [media, ...project.media_assets],
        });
        setToast({
          type: "success",
          message: "Import finished — the new video has been added to this project.",
        });
      } catch (err) {
        console.error("Failed to load ingested media:", err);
      }
    });
  }, [jobs, project, onMediaUpdated]);

  // Report real stats to App layout for the status bar
  useEffect(() => {
    onStatsChange?.({
      clipCount: candidates.length,
      hasTranscript: transcripts.length > 0,
    });
  }, [candidates.length, transcripts.length, onStatsChange]);

  // When candidate_thumbnails job succeeds, bump thumbnailEpoch to reload cards
  useEffect(() => {
    const succeededThumbs = jobs.filter(
      (j) =>
        j.type === "candidate_thumbnails" &&
        j.status === "succeeded" &&
        !handledThumbnailJobIds.current.has(j.id),
    );
    if (succeededThumbs.length > 0) {
      succeededThumbs.forEach((j) => handledThumbnailJobIds.current.add(j.id));
      setThumbnailEpoch((e) => e + 1);
    }
  }, [jobs]);

  // Map candidate IDs to their rendered download URLs
  const renderedCandidateMap = useMemo(() => {
    const map = new Map<string, string>();
    jobs
      .filter((j) => j.type === "render" && j.status === "succeeded")
      .forEach((j) => {
        try {
          const parsed = JSON.parse(j.config_json || "{}");
          const candId = parsed.candidate_id;
          if (candId) {
            map.set(candId, `/api/candidates/${encodeURIComponent(candId)}/render-file`);
          }
        } catch {
          // ignore
        }
      });
    return map;
  }, [jobs]);

  const activeRenderJob = jobs.find(
    (j) => j.type === "render" && (j.status === "queued" || j.status === "running"),
  );
  const isExporting = Boolean(activeRenderJob);
  const exportProgress = activeRenderJob ? Math.round(activeRenderJob.progress) : 0;

  useEffect(() => {
    if (!hasActiveJob) return;
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [hasActiveJob]);

  const formatElapsedSeconds = (startedAt: string | null): string => {
    if (!startedAt || !nowMs) return "--:--";
    const elapsedMs = Math.max(0, nowMs - new Date(startedAt).getTime());
    const secs = Math.max(0, Math.floor(elapsedMs / 1000));
    const minutes = Math.floor(secs / 60);
    return `${minutes}m ${secs % 60}s`;
  };

  const formatDuration = (ms: number): string => {
    const totalSeconds = Math.floor(ms / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
  };

  const formatSize = (bytes: number): string => {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const handleMediaUploaded = (newMedia: MediaAsset) => {
    const updated = {
      ...project,
      media_count: project.media_count + 1,
      media_assets: [newMedia, ...project.media_assets],
    };
    onMediaUpdated(updated);
    setShowUploader(false);
  };

  const handleDelete = async () => {
    setConfirmRequest({
      title: `Delete "${project.name}"?`,
      message:
        "The project and all local media files will be permanently removed. This action cannot be undone.",
      confirmLabel: "Delete Project",
      onConfirm: async () => {
        setIsDeleting(true);
        try {
          await onDeleteProject(project.id);
        } finally {
          setIsDeleting(false);
          setConfirmRequest(null);
        }
      },
    });
  };

  const handleStartExtraction = async (mediaId: string) => {
    setIsSubmittingJob(true);
    try {
      const newJob = await api.createAudioExtractionJob(mediaId);
      setJobs((prev) => [newJob, ...prev.filter((j) => j.id !== newJob.id)]);
    } catch (err) {
      console.error("Failed to enqueue audio extraction job:", err);
      setToast({
        type: "error",
        message: `Could not start extraction: ${err instanceof Error ? err.message : String(err)}`,
      });
    } finally {
      setIsSubmittingJob(false);
    }
  };

  const handleCancelJob = async (jobId: string) => {
    setCancellingJobId(jobId);
    try {
      const updated = await api.cancelJob(jobId);
      setJobs((prev) => prev.map((j) => (j.id === jobId ? updated : j)));
    } catch (err) {
      console.error("Failed to cancel job:", err);
    } finally {
      setCancellingJobId(null);
    }
  };

  const handleClearJobs = async () => {
    setConfirmRequest({
      title: "Clear job history?",
      message:
        "All completed, cancelled, and failed background jobs will be removed from this project's history. Running jobs are kept.",
      confirmLabel: "Clear Jobs",
      onConfirm: async () => {
        setIsClearingJobs(true);
        try {
          await api.clearProjectJobs(project.id);
          await fetchJobs();
        } catch (err) {
          console.error("Failed to clear project jobs:", err);
          setToast({
            type: "error",
            message: `Could not clear job history: ${err instanceof Error ? err.message : String(err)}`,
          });
        } finally {
          setIsClearingJobs(false);
          setConfirmRequest(null);
        }
      },
    });
  };

  const handleStartTranscription = async (req: TranscriptionRequest) => {
    if (!primaryMedia) return;
    setIsSubmittingTranscription(true);
    try {
      const newJob = await api.createTranscriptionJob(primaryMedia.id, req);
      setJobs((prev) => [newJob, ...prev.filter((j) => j.id !== newJob.id)]);
    } catch (err) {
      console.error("Failed to enqueue transcription job:", err);
      setToast({
        type: "error",
        message: `Could not start transcription: ${
          err instanceof Error ? err.message : String(err)
        }`,
      });
    } finally {
      setIsSubmittingTranscription(false);
    }
  };

  const renderJobStatusBadge = (status: JobStatus) => {
    switch (status) {
      case "queued":
        return (
          <span className="inline-flex items-center space-x-1 text-xs text-amber-400 bg-amber-950/50 border border-amber-800/40 px-2.5 py-0.5 rounded-full">
            <Clock className="h-3 w-3" />
            <span className="capitalize">Queued</span>
          </span>
        );
      case "running":
        return (
          <span className="inline-flex items-center space-x-1 text-xs text-cyan-400 bg-cyan-950/50 border border-cyan-800/40 px-2.5 py-0.5 rounded-full">
            <Loader2 className="h-3 w-3 animate-spin" />
            <span className="capitalize">Running</span>
          </span>
        );
      case "succeeded":
        return (
          <span className="inline-flex items-center space-x-1 text-xs text-emerald-400 bg-emerald-950/50 border border-emerald-800/40 px-2.5 py-0.5 rounded-full">
            <CheckCircle2 className="h-3 w-3" />
            <span className="capitalize">Succeeded</span>
          </span>
        );
      case "failed":
        return (
          <span className="inline-flex items-center space-x-1 text-xs text-red-400 bg-red-950/50 border border-red-800/40 px-2.5 py-0.5 rounded-full">
            <AlertCircle className="h-3 w-3" />
            <span className="capitalize">Failed</span>
          </span>
        );
      case "cancelled":
        return (
          <span className="inline-flex items-center space-x-1 text-xs text-slate-400 bg-slate-800/60 border border-slate-700/60 px-2.5 py-0.5 rounded-full">
            <XCircle className="h-3 w-3" />
            <span className="capitalize">Cancelled</span>
          </span>
        );
    }
  };

  return (
    <div className="space-y-5">
      {/* Global confirmation + feedback overlays */}
      <ConfirmDialog
        isOpen={Boolean(confirmRequest)}
        title={confirmRequest?.title ?? ""}
        message={confirmRequest?.message ?? ""}
        confirmLabel={confirmRequest?.confirmLabel ?? "Confirm"}
        isDestructive
        isConfirming={isConfirming}
        onClose={() => setConfirmRequest(null)}
        onConfirm={() => {
          setIsConfirming(true);
          void Promise.resolve(confirmRequest?.onConfirm()).finally(() => setIsConfirming(false));
        }}
      />
      {toast && <Toast type={toast.type} message={toast.message} onClose={() => setToast(null)} />}
      <YouTubeImportModal
        isOpen={isYouTubeModalOpen}
        onClose={() => setIsYouTubeModalOpen(false)}
        projectId={project.id}
        onQueued={(_jobId) => {
          setToast({
            type: "info",
            message: "Import job queued — the video will appear here when the download finishes.",
          });
          void fetchJobs();
        }}
      />

      {/* Top action bar */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 rounded-2xl border border-slate-800/80 bg-obsidian-900/60 backdrop-blur-md px-4 sm:px-5 py-4 shadow-panel">
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={onBack}
            className="p-2 text-slate-400 hover:text-white bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded-xl transition-colors cursor-pointer shrink-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
            aria-label="Back to projects"
            title="Back to projects"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          </button>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              {isEditingName ? (
                <div className="flex items-center gap-1.5">
                  <input
                    type="text"
                    value={editingName}
                    onChange={(e) => setEditingName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleSaveName();
                      if (e.key === "Escape") {
                        setEditingName(project.name);
                        setIsEditingName(false);
                      }
                    }}
                    autoFocus
                    dir="auto"
                    aria-label="Project name"
                    className="px-2.5 py-1 rounded-lg bg-obsidian-950 border border-purple-500 text-base font-bold text-white focus:outline-none"
                  />
                  <button
                    onClick={handleSaveName}
                    disabled={isSavingName || !editingName.trim()}
                    className="p-1.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-white disabled:opacity-50 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
                    title="Save"
                    aria-label="Save project name"
                  >
                    <Check className="h-4 w-4" aria-hidden="true" />
                  </button>
                  <button
                    onClick={() => {
                      setEditingName(project.name);
                      setIsEditingName(false);
                    }}
                    className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
                    title="Cancel"
                    aria-label="Cancel project rename"
                  >
                    <X className="h-4 w-4" aria-hidden="true" />
                  </button>
                </div>
              ) : (
                <div className="flex items-center gap-2 group min-w-0">
                  <h2 dir="auto" className="text-xl font-bold text-white tracking-tight truncate">
                    {project.name}
                  </h2>
                  {onRenameProject && (
                    <button
                      onClick={() => {
                        setEditingName(project.name);
                        setIsEditingName(true);
                      }}
                      className="p-1 text-slate-500 hover:text-laqta-300 rounded-lg hover:bg-slate-800 transition opacity-70 group-hover:opacity-100 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
                      title="Rename Project"
                      aria-label="Rename project"
                    >
                      <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                    </button>
                  )}
                  <span className="text-[11px] font-mono text-slate-400 bg-slate-900 border border-slate-800 px-2 py-0.5 rounded">
                    {project.id}
                  </span>
                </div>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
              <span className="inline-flex items-center gap-1 rounded-md border border-slate-800 bg-obsidian-950/60 px-1.5 py-0.5 text-[10px] font-mono text-slate-400">
                <Calendar className="h-3 w-3" aria-hidden="true" />
                Created {new Date(project.created_at).toLocaleDateString()}
              </span>
              <span className="inline-flex items-center gap-1 rounded-md border border-slate-800 bg-obsidian-950/60 px-1.5 py-0.5 text-[10px] font-mono text-slate-400">
                <FileVideo className="h-3 w-3" aria-hidden="true" />
                {project.media_count || project.media_assets.length}{" "}
                {project.media_count === 1 ? "media file" : "media files"}
              </span>
              <span className="inline-flex items-center gap-1 rounded-md border border-laqta-800/60 bg-laqta-950/50 px-1.5 py-0.5 text-[10px] font-mono text-laqta-200">
                <Clapperboard className="h-3 w-3" aria-hidden="true" />
                {candidates.length} clip {candidates.length === 1 ? "candidate" : "candidates"}
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={handleDelete}
            disabled={isDeleting}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-red-400 hover:text-red-300 hover:bg-red-950/40 border border-red-900/40 transition-colors disabled:opacity-50 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
          >
            <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
            <span>{isDeleting ? "Deleting..." : "Delete Project"}</span>
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      {!hasMedia || showUploader ? (
        <div className="space-y-4">
          {/* Import Your Video hero card */}
          <div className="rounded-2xl border border-slate-800/80 bg-obsidian-900/60 backdrop-blur-md p-5 sm:p-6">
            <div className="flex flex-col lg:flex-row lg:items-center gap-5">
              <div className="flex items-center space-x-3.5 min-w-0">
                <div className="p-3 rounded-xl bg-linear-to-br from-laqta-600/25 to-cyan-500/20 border border-laqta-700/50 text-laqta-200 shadow-neon-purple shrink-0">
                  <UploadCloud className="h-5 w-5" />
                </div>
                <div className="min-w-0">
                  <h3 className="text-base font-bold text-white tracking-tight">
                    {showUploader ? "Import Additional Video" : "Import Your Video"}
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Upload a local file or paste a YouTube link
                  </p>
                </div>
              </div>

              <div className="flex items-center flex-wrap gap-3 lg:ml-auto shrink-0">
                <button
                  type="button"
                  onClick={() => {
                    document.getElementById("media-uploader-dropzone")?.click();
                  }}
                  className="inline-flex items-center justify-center px-5 py-2.5 rounded-xl laqta-gradient-surface hover:brightness-110 text-white text-sm font-semibold shadow-laqta-glow transition-[filter,transform] active:scale-[0.98] cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
                >
                  <UploadCloud className="h-4 w-4 mr-2" aria-hidden="true" />
                  Upload File
                  <span className="ml-2 text-[10px] font-normal opacity-80">
                    MP4, MOV, MKV (max 4 GB)
                  </span>
                </button>

                {urlIngestionReady ? (
                  <button
                    type="button"
                    onClick={() => setIsYouTubeModalOpen(true)}
                    className="relative inline-flex flex-col items-start px-5 py-2 rounded-xl bg-slate-800/60 hover:bg-slate-700/60 border border-slate-700/60 text-slate-200 hover:text-white text-sm font-medium transition cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
                  >
                    <span className="inline-flex items-center space-x-1.5">
                      <YouTubeIcon className="h-4 w-4 text-red-400" />
                      <span>YouTube Link</span>
                    </span>
                    <span className="text-[10px] text-slate-400">Paste URL here</span>
                  </button>
                ) : (
                  /* Fail-closed when the operator disabled ingestion (PRD FR-12):
                     visible refusal instead of a fake button. */
                  <button
                    type="button"
                    disabled
                    title={
                      urlIngestion?.feature_flag
                        ? "yt-dlp is not installed on this machine. Install yt-dlp to enable YouTube import."
                        : "YouTube import is disabled on the backend (QATTA_ENABLE_URL_INGESTION=false). Remove the override to re-enable it; imports still require yt-dlp and a rights confirmation."
                    }
                    aria-disabled="true"
                    className="relative inline-flex flex-col items-start px-5 py-2 rounded-xl bg-slate-800/60 border border-slate-700/60 text-slate-400 text-sm font-medium cursor-not-allowed opacity-70"
                  >
                    <span className="inline-flex items-center space-x-1.5">
                      <YouTubeIcon className="h-4 w-4 text-red-400" />
                      <span>YouTube Link</span>
                    </span>
                    <span className="text-[10px] text-slate-500">Paste URL here</span>
                    <span
                      className="absolute -top-1.5 -right-1.5 h-2.5 w-2.5 rounded-full bg-amber-400 border border-slate-900"
                      aria-hidden="true"
                    />
                  </button>
                )}

                {showUploader && (
                  <button
                    onClick={() => setShowUploader(false)}
                    className="text-xs text-slate-400 hover:text-white transition focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 rounded cursor-pointer"
                  >
                    Cancel
                  </button>
                )}
              </div>
            </div>
          </div>
          <MediaUploader projectId={project.id} onMediaUploaded={handleMediaUploaded} />
        </div>
      ) : (
        primaryMedia && (
          <div className="space-y-6">
            {/* Probed Stream Specifications & Studio Controls */}
            <div className="bg-obsidian-900/70 border border-slate-800/80 rounded-2xl shadow-panel backdrop-blur-md overflow-hidden">
              <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 px-4 sm:px-5 py-3.5">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="p-2.5 bg-laqta-950/60 border border-laqta-700/50 rounded-xl text-laqta-200 shadow-sm shrink-0">
                    <FileVideo className="h-5 w-5" aria-hidden="true" />
                  </div>
                  <div className="min-w-0">
                    <h3
                      dir="auto"
                      className="text-base font-semibold text-white tracking-tight break-words"
                    >
                      {primaryMedia.original_name}
                    </h3>
                    <div className="flex items-center flex-wrap gap-x-2 gap-y-0.5 text-[11px] text-slate-400 mt-0.5 font-mono">
                      <span>{primaryMedia.id}</span>
                      <span className="text-slate-700" aria-hidden="true">
                        •
                      </span>
                      <span>{formatSize(primaryMedia.size_bytes)}</span>
                      <span className="text-slate-700" aria-hidden="true">
                        •
                      </span>
                      <span className="text-emerald-400 font-medium capitalize font-sans">
                        Status: {primaryMedia.status}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-emerald-400 bg-emerald-950/50 border border-emerald-800/40 px-2.5 py-1 rounded-full">
                    <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                    <span>FFprobe Verified</span>
                  </span>

                  <button
                    onClick={() => handleStartExtraction(primaryMedia.id)}
                    disabled={isSubmittingJob || jobs.some((j) => j.status === "running")}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold text-white laqta-gradient-surface hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed transition-[filter] shadow-laqta-glow cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
                  >
                    {isSubmittingJob ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                    ) : (
                      <Music className="h-3.5 w-3.5" aria-hidden="true" />
                    )}
                    <span>Extract Audio (16 kHz)</span>
                  </button>

                  <button
                    onClick={() => setShowUploader(true)}
                    className="px-3 py-1.5 rounded-xl text-xs font-medium text-slate-300 hover:text-white bg-slate-800/60 hover:bg-slate-700/60 border border-slate-700/60 transition cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
                  >
                    Replace Video
                  </button>

                  {/* Studio View Mode Switcher */}
                  <div
                    className="inline-flex rounded-xl bg-obsidian-950 p-1 border border-slate-800"
                    role="tablist"
                    aria-label="Workbench mode"
                  >
                    <button
                      type="button"
                      role="tab"
                      aria-selected={studioViewMode === "studio"}
                      onClick={() => setStudioViewMode("studio")}
                      className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 ${
                        studioViewMode === "studio"
                          ? "laqta-gradient-surface text-white shadow-laqta-glow"
                          : "text-slate-400 hover:text-white"
                      }`}
                    >
                      <Sparkles className="h-3 w-3" aria-hidden="true" />
                      <span>Studio</span>
                    </button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={studioViewMode === "diagnostics"}
                      onClick={() => setStudioViewMode("diagnostics")}
                      className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 ${
                        studioViewMode === "diagnostics"
                          ? "bg-slate-800 text-white border border-slate-700"
                          : "text-slate-400 hover:text-white"
                      }`}
                    >
                      <Layers className="h-3 w-3" aria-hidden="true" />
                      <span>Diagnostics</span>
                    </button>
                  </div>
                </div>
              </div>

              {/* Probed Stream Specifications — compact strip */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-px bg-slate-800/70 border-t border-slate-800/70">
                <div
                  className="flex items-center gap-2.5 bg-obsidian-900/90 px-4 py-2.5"
                  title={`${primaryMedia.duration_ms} ms`}
                >
                  <Clock className="h-4 w-4 text-slate-500 shrink-0" aria-hidden="true" />
                  <div className="min-w-0">
                    <p className="text-[10px] uppercase tracking-[0.12em] text-slate-500">
                      Duration
                    </p>
                    <p className="text-sm font-bold text-white font-mono leading-tight">
                      {formatDuration(primaryMedia.duration_ms)}
                    </p>
                  </div>
                </div>

                <div
                  className="flex items-center gap-2.5 bg-obsidian-900/90 px-4 py-2.5"
                  title={
                    primaryMedia.width < primaryMedia.height
                      ? "Vertical (9:16)"
                      : "Landscape (16:9)"
                  }
                >
                  <Monitor className="h-4 w-4 text-slate-500 shrink-0" aria-hidden="true" />
                  <div className="min-w-0">
                    <p className="text-[10px] uppercase tracking-[0.12em] text-slate-500">
                      Resolution
                    </p>
                    <p className="text-sm font-bold text-white font-mono leading-tight">
                      {primaryMedia.width} × {primaryMedia.height}
                    </p>
                  </div>
                </div>

                <div
                  className="flex items-center gap-2.5 bg-obsidian-900/90 px-4 py-2.5"
                  title="Hardware decoding ready"
                >
                  <Film className="h-4 w-4 text-slate-500 shrink-0" aria-hidden="true" />
                  <div className="min-w-0">
                    <p className="text-[10px] uppercase tracking-[0.12em] text-slate-500">
                      Video Codec
                    </p>
                    <p className="text-sm font-bold text-white font-mono uppercase leading-tight">
                      {primaryMedia.video_codec.toUpperCase()}
                    </p>
                  </div>
                </div>

                <div
                  className="flex items-center gap-2.5 bg-obsidian-900/90 px-4 py-2.5"
                  title={
                    primaryMedia.audio_codec !== "none" ? "Audio track detected" : "Muted video"
                  }
                >
                  <Volume2 className="h-4 w-4 text-slate-500 shrink-0" aria-hidden="true" />
                  <div className="min-w-0">
                    <p className="text-[10px] uppercase tracking-[0.12em] text-slate-500">
                      Audio Stream
                    </p>
                    <p className="text-sm font-bold text-white font-mono uppercase leading-tight">
                      {primaryMedia.audio_codec.toUpperCase()}
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Backend Offline Warning Banner */}
            {isBackendOffline && (
              <div
                className="bg-red-950/70 border border-red-800/80 rounded-2xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-red-200 shadow-xl"
                data-testid="backend-offline-banner"
              >
                <div className="flex items-center space-x-3">
                  <div className="p-2 bg-red-900/40 rounded-xl text-red-400">
                    <AlertCircle className="h-5 w-5" />
                  </div>
                  <div>
                    <h4 className="text-xs font-bold text-white">
                      Local Backend Offline (127.0.0.1:8000)
                    </h4>
                    <p className="text-[11px] text-red-300 mt-0.5">
                      The FastAPI backend service is currently unreachable. Start it with{" "}
                      <code className="font-mono bg-red-900/60 px-1 py-0.5 rounded text-white">
                        uvicorn app.main:app
                      </code>
                      .
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => fetchJobs()}
                  className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold text-white bg-red-800 hover:bg-red-700 border border-red-600 transition cursor-pointer self-start sm:self-auto"
                >
                  <RotateCw className="h-3.5 w-3.5" />
                  <span>Retry Connection</span>
                </button>
              </div>
            )}

            {/* Neon AI Studio Workbench View */}
            {studioViewMode === "studio" && (
              <div className="space-y-6">
                {/* 3-Column Studio Workbench */}
                <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 items-stretch">
                  {/* Left Column: AI Suggested Clips */}
                  <div className="xl:col-span-4 h-[clamp(560px,74vh,900px)] min-h-0">
                    <SuggestedClipsList
                      candidates={candidates}
                      selectedCandidateId={selectedCandidate?.id ?? null}
                      onSelectCandidate={handleSelectCandidate}
                      mediaId={primaryMedia.id}
                      isAnalyzing={isGeneratingCandidates}
                      onGenerateCandidates={handleGenerateCandidates}
                      segments={transcripts[0]?.segments ?? []}
                      hasTranscript={transcripts.length > 0}
                      thumbnailEpoch={thumbnailEpoch}
                      renderedCandidateMap={renderedCandidateMap}
                      isTranscribing={
                        isSubmittingTranscription ||
                        jobs.some(
                          (j) =>
                            j.type === "transcription" &&
                            (j.status === "queued" || j.status === "running"),
                        )
                      }
                      transcriptionProgress={
                        jobs.find(
                          (j) =>
                            j.type === "transcription" &&
                            (j.status === "queued" || j.status === "running"),
                        )?.progress ?? 0
                      }
                      transcriptionStage={
                        jobs.find(
                          (j) =>
                            j.type === "transcription" &&
                            (j.status === "queued" || j.status === "running"),
                        )?.stage ?? "queued"
                      }
                      onStartTranscription={(profile, lang) =>
                        handleStartTranscription({
                          profile,
                          language: lang || undefined,
                        })
                      }
                      onSeekSegment={(sec) => setCurrentTimeSec(sec)}
                    />
                  </div>

                  {/* Center Column: Preview Panel Header + 9:16 Canvas Player */}
                  <div className="xl:col-span-4 2xl:col-span-5 h-[clamp(560px,74vh,900px)] min-h-0 flex flex-col rounded-2xl border border-slate-800/80 bg-obsidian-900/60 backdrop-blur-md overflow-hidden shadow-panel">
                    {/* Preview Panel Header */}
                    <div className="shrink-0 flex items-start justify-between gap-3 px-4 py-3 border-b border-slate-800/80">
                      <div className="min-w-0">
                        <h4
                          dir="auto"
                          className="text-sm font-bold text-white tracking-tight truncate"
                          title={cleanDisplayText(
                            selectedCandidate?.title || primaryMedia.original_name,
                          )}
                        >
                          {cleanDisplayText(selectedCandidate?.title || primaryMedia.original_name)}
                        </h4>
                        <div className="flex items-center flex-wrap gap-x-2 text-[11px] text-slate-400 mt-0.5 font-mono">
                          <span>{formatDuration(primaryMedia.duration_ms)}</span>
                          <span className="text-slate-700" aria-hidden="true">
                            •
                          </span>
                          <span>
                            {primaryMedia.width}×{primaryMedia.height}
                          </span>
                          <span className="text-slate-700" aria-hidden="true">
                            •
                          </span>
                          <span>{formatSize(primaryMedia.size_bytes)}</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        {candidates.length > 0 && (
                          <span
                            className="inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-300 bg-emerald-950/70 border border-emerald-800/60 px-2.5 py-1 rounded-full"
                            data-testid="analysis-complete-badge"
                          >
                            <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                            <span>Analysis Complete</span>
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Canvas Player Body */}
                    <div className="flex-1 min-h-0 flex items-center justify-center p-2 sm:p-3">
                      <ShortsCanvasPlayer
                        mediaUrl={generateMediaFileUrl(primaryMedia.id)}
                        mediaTitle={cleanDisplayText(
                          selectedCandidate?.title || primaryMedia.original_name,
                        )}
                        aspectRatio={aspectRatio}
                        onChangeAspectRatio={(r) => {
                          setAspectRatio(r);
                          handleUpdateEditSettings({ aspectRatio: r });
                        }}
                        showSpeakerGuide={showSpeakerGuide}
                        onToggleSpeakerGuide={() => setShowSpeakerGuide((prev) => !prev)}
                        segments={transcripts[0]?.segments ?? []}
                        captionStyle={{
                          position: captionOptions.position,
                          fontSize: captionOptions.fontSize,
                          highlightColor: captionOptions.highlightColor,
                          karaokeSync: captionOptions.karaokeSync,
                          preset: captionOptions.preset,
                          fontFamily: captionOptions.fontFamily,
                          textColor: captionOptions.textColor,
                        }}
                        currentTimeSec={currentTimeSec}
                        durationSec={primaryMedia.duration_ms / 1000}
                        isPlaying={isPlaying}
                        onTogglePlay={() => setIsPlaying((prev) => !prev)}
                        onSeek={(sec) => setCurrentTimeSec(sec)}
                        onTimeUpdate={(sec) => setCurrentTimeSec(sec)}
                        clipWindow={
                          selectedCandidate
                            ? {
                                startSec: selectedCandidate.start_ms / 1000,
                                endSec: selectedCandidate.end_ms / 1000,
                              }
                            : null
                        }
                      />
                    </div>
                  </div>

                  {/* Right Column: Inspector Panel (Edit, Captions, Export) */}
                  <div className="xl:col-span-4 2xl:col-span-3 h-[clamp(560px,74vh,900px)] min-h-0">
                    <InspectorPanel
                      activeTab={inspectorTab}
                      onTabChange={setInspectorTab}
                      editSettings={editSettings}
                      onUpdateEditSettings={handleUpdateEditSettings}
                      captionOptions={captionOptions}
                      onUpdateCaptionOptions={handleUpdateCaptionOptions}
                      exportSettings={exportSettings}
                      onUpdateExportSettings={handleUpdateExportSettings}
                      onExport={handleExport}
                      sourceDurationSec={primaryMedia.duration_ms / 1000}
                      isExporting={isExporting}
                      exportProgress={exportProgress}
                      downloadUrl={
                        selectedCandidate
                          ? (renderedCandidateMap.get(selectedCandidate.id) ?? null)
                          : null
                      }
                    />
                  </div>
                </div>

                {/* Bottom Row: Multi-Track Interactive Timeline */}
                <MultiTrackTimeline
                  currentTimeSec={currentTimeSec}
                  durationSec={primaryMedia.duration_ms / 1000}
                  onSeek={(sec) => setCurrentTimeSec(sec)}
                  activeClipWindow={
                    selectedCandidate
                      ? {
                          startSec: selectedCandidate.start_ms / 1000,
                          endSec: selectedCandidate.end_ms / 1000,
                        }
                      : {
                          startSec: editSettings.startSec,
                          endSec: editSettings.endSec,
                        }
                  }
                  segments={transcripts[0]?.segments ?? []}
                  onSelectSegment={(seg) => setCurrentTimeSec(seg.start)}
                  zoomPrefix="Zoom: "
                />
              </div>
            )}

            {/* Diagnostics View — the single, explicit way to reach the
                transcription diagnostics and the candidate editor. The
                Studio | Diagnostics switch above is the only entry point
                (no duplicated expander below the timeline). */}
            {studioViewMode === "diagnostics" && (
              <div className="space-y-6 pt-2">
                {/* Speech Transcription Section */}
                <TranscriptViewer
                  mediaId={primaryMedia.id}
                  transcripts={transcripts}
                  isLoading={isLoadingTranscripts}
                  isFasterWhisperAvailable={localCapabilities?.asr?.faster_whisper ?? false}
                  isTranscribing={
                    isSubmittingTranscription ||
                    jobs.some(
                      (j) =>
                        j.type === "transcription" &&
                        (j.status === "queued" || j.status === "running"),
                    )
                  }
                  onStartTranscription={handleStartTranscription}
                  onRefreshTranscripts={() => fetchTranscripts(primaryMedia.id)}
                />

                {/* Candidate Clips: review/edit (user journey steps 7-10) */}
                <CandidatesPanel
                  mediaId={primaryMedia.id}
                  mediaDurationMs={primaryMedia.duration_ms}
                  transcripts={transcripts}
                  transcriptionJob={latestTranscriptionJobState(jobs)}
                  onRetryTranscription={() =>
                    handleStartTranscription({
                      profile: "fast",
                    })
                  }
                />
              </div>
            )}

            {/* Background Jobs Section */}
            <div className="bg-obsidian-900/70 border border-slate-800/80 rounded-2xl p-5 shadow-lg space-y-4 backdrop-blur-md">
              <div className="flex items-center justify-between pb-3 border-b border-slate-800/80">
                <div className="flex items-center space-x-2.5">
                  <h3 className="text-sm font-bold text-white tracking-tight">Processing Jobs</h3>
                  <span className="text-xs text-slate-500 font-mono">({jobs.length})</span>
                  {jobs.some((j) => j.status === "failed") && (
                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-red-950/70 text-red-300 border border-red-800/50">
                      {jobs.filter((j) => j.status === "failed").length} failed/interrupted
                    </span>
                  )}
                  {jobs.some((j) => j.status === "succeeded") && (
                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-950/70 text-emerald-300 border border-emerald-800/50">
                      {jobs.filter((j) => j.status === "succeeded").length} succeeded
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  {jobs.some((j) => j.status !== "queued" && j.status !== "running") && (
                    <button
                      onClick={handleClearJobs}
                      disabled={isClearingJobs}
                      className="px-2.5 py-1 text-slate-400 hover:text-red-300 hover:bg-red-950/30 border border-slate-800 hover:border-red-900/40 rounded-xl text-xs flex items-center gap-1.5 transition cursor-pointer disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
                      title="Clear completed and failed jobs history"
                    >
                      <Trash2 className="h-3 w-3" aria-hidden="true" />
                      <span>{isClearingJobs ? "Clearing..." : "Clear History"}</span>
                    </button>
                  )}

                  <button
                    onClick={() => fetchJobs()}
                    className="p-1.5 text-slate-400 hover:text-white bg-obsidian-950 border border-slate-800 rounded-xl text-xs flex items-center gap-1 cursor-pointer transition focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
                    title="Refresh jobs"
                  >
                    <RotateCw className="h-3.5 w-3.5" aria-hidden="true" />
                    <span>Refresh</span>
                  </button>

                  <button
                    onClick={() => setIsJobHistoryOpen((prev) => !prev)}
                    className="p-1.5 text-slate-400 hover:text-white bg-obsidian-950 border border-slate-800 rounded-xl text-xs transition cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
                    aria-label={isJobHistoryOpen ? "Collapse jobs" : "Expand jobs"}
                  >
                    {isJobHistoryOpen ? (
                      <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" />
                    ) : (
                      <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
                    )}
                  </button>
                </div>
              </div>

              {isJobHistoryOpen && (
                <>
                  {isLoadingJobs && jobs.length === 0 ? (
                    <div className="py-6 text-center text-xs text-slate-500 flex items-center justify-center space-x-2">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      <span>Loading jobs...</span>
                    </div>
                  ) : jobs.length === 0 ? (
                    <div className="py-8 text-center text-xs text-slate-500">
                      No background jobs run yet for this project. Click &ldquo;Extract Audio&rdquo;
                      to begin.
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {jobs.map((job) => (
                        <div
                          key={job.id}
                          className="rounded-xl border border-slate-800/80 bg-slate-950/60 px-3 py-2.5 transition-colors hover:border-slate-700/80"
                          data-testid={`job-row-${job.id}`}
                        >
                          <div className="flex items-center gap-2.5 flex-wrap">
                            {renderJobStatusBadge(job.status)}
                            <span className="text-xs font-mono font-medium text-slate-200">
                              {job.type}
                            </span>
                            <span className="text-[11px] font-mono text-slate-400">{job.id}</span>

                            <div className="flex items-center gap-2 ml-auto">
                              {(job.status === "queued" || job.status === "running") && (
                                <button
                                  onClick={() => handleCancelJob(job.id)}
                                  disabled={cancellingJobId === job.id}
                                  className="inline-flex items-center space-x-1 text-xs text-red-400 hover:text-red-300 hover:bg-red-950/40 border border-red-900/40 px-2.5 py-1 rounded-lg transition disabled:opacity-50 cursor-pointer"
                                >
                                  {cancellingJobId === job.id ? (
                                    <Loader2 className="h-3 w-3 animate-spin" />
                                  ) : (
                                    <XCircle className="h-3 w-3" />
                                  )}
                                  <span>Cancel</span>
                                </button>
                              )}
                              {(job.status === "failed" || job.status === "cancelled") &&
                                primaryMedia && (
                                  <button
                                    onClick={() => {
                                      if (job.type === "transcription") {
                                        handleStartTranscription({
                                          profile: "fast",
                                        });
                                      } else if (job.type === "audio_extraction") {
                                        handleStartExtraction(primaryMedia.id);
                                      }
                                    }}
                                    disabled={isSubmittingTranscription || isSubmittingJob}
                                    className="inline-flex items-center space-x-1 text-xs text-laqta-300 hover:text-laqta-200 hover:bg-laqta-950/40 border border-laqta-900/50 px-2.5 py-1 rounded-lg transition disabled:opacity-50 cursor-pointer"
                                  >
                                    <RotateCw className="h-3 w-3" />
                                    <span>Retry</span>
                                  </button>
                                )}
                              {job.status === "succeeded" && job.type === "render" && (
                                <a
                                  href={`/api/candidates/${(() => {
                                    try {
                                      return (
                                        JSON.parse(job.config_json || "{}").candidate_id ||
                                        selectedCandidate?.id ||
                                        ""
                                      );
                                    } catch {
                                      return selectedCandidate?.id || "";
                                    }
                                  })()}/render-file`}
                                  download
                                  className="inline-flex items-center space-x-1 text-xs text-neon-emerald hover:text-emerald-300 hover:bg-emerald-950/40 border border-emerald-900/40 px-2.5 py-1 rounded-lg transition font-semibold"
                                  data-testid="download-short-link"
                                >
                                  <Download className="h-3 w-3" />
                                  <span>Download Short</span>
                                </a>
                              )}
                            </div>
                          </div>

                          {/* Progress: one thin bar with the percentage and the
                          stage inline, so a job costs a single scan line.
                          Finished jobs keep the bar muted — a full-width
                          emerald bar for every finished job is noise. */}
                          <div className="mt-2 flex items-center gap-2.5">
                            {job.status === "queued" || job.status === "running" ? (
                              <div className="flex-1 h-1.5 bg-slate-900 rounded-full overflow-hidden">
                                <div
                                  className="h-full laqta-gradient-surface transition-all duration-300"
                                  style={{ width: `${Math.max(job.progress, 2)}%` }}
                                />
                              </div>
                            ) : (
                              <div className="flex-1 h-1.5 bg-slate-900 rounded-full overflow-hidden">
                                <div
                                  className={`h-full transition-all duration-300 ${
                                    job.status === "succeeded"
                                      ? "bg-emerald-500/30"
                                      : job.status === "failed"
                                        ? "bg-red-500/40"
                                        : "bg-slate-600/50"
                                  }`}
                                  style={{ width: `${Math.max(job.progress, 2)}%` }}
                                />
                              </div>
                            )}
                            <span className="text-[10px] font-mono text-slate-400 shrink-0 tabular-nums w-[74px] text-right">
                              {job.indeterminate
                                ? `elapsed ${formatElapsedSeconds(job.started_at)}`
                                : `${Math.round(job.progress)}%`}
                            </span>
                            <span className="text-[10px] font-mono text-slate-400 capitalize shrink-0">
                              {job.stage}
                            </span>
                          </div>

                          {/* Timestamps & Diagnostic Info */}
                          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[10px] font-mono text-slate-400">
                            <span>submitted {new Date(job.created_at).toLocaleTimeString()}</span>
                            {job.started_at && (
                              <span>started {new Date(job.started_at).toLocaleTimeString()}</span>
                            )}
                            {job.finished_at && (
                              <span>finished {new Date(job.finished_at).toLocaleTimeString()}</span>
                            )}
                            {job.started_at && !job.finished_at && (
                              <span>elapsed {formatElapsedSeconds(job.started_at)}</span>
                            )}
                          </div>

                          {job.error_code && (
                            <div className="mt-2 p-2.5 rounded-lg bg-red-950/30 border border-red-900/40 text-red-300">
                              <div className="font-mono text-[11px] font-semibold text-red-400">
                                Error [{job.error_code}]
                              </div>
                              <div className="text-xs mt-0.5">{job.error_message}</div>
                              {job.error_code === "INTERRUPTED_ON_RESTART" && (
                                <div className="text-[11px] text-amber-300 mt-1 font-sans">
                                  Notice: The job was safely interrupted when the server restarted
                                  and did not corrupt any media. You can safely retry it.
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        )
      )}
    </div>
  );
};
