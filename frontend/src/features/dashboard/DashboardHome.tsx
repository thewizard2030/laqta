import React, { useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  Clapperboard,
  Clock,
  FileVideo,
  Film,
  FolderKanban,
  HardDrive,
  Layers,
  Loader2,
  Lock,
  Mic,
  Plus,
  Gauge,
  ShieldCheck,
  UploadCloud,
  Video,
  Youtube,
} from "lucide-react";
import { ProjectPoster } from "../../components/studio/ProjectPoster";
import { Toast, ToastType } from "../../components/ui/Toast";
import { EmptyState } from "../../components/EmptyState";
import { YouTubeImportModal } from "../projects/YouTubeImportModal";
import { EngineStatusStrip } from "./EngineStatusStrip";
import { YouTubeTargetModal } from "./YouTubeTargetModal";
import { CapabilitiesResponse } from "../../types/capabilities";
import { HealthResponse } from "../../types/health";
import { Project } from "../../types/projects";
import {
  formatBytes,
  formatDurationHuman,
  formatDurationMs,
  formatRelativeTime,
} from "../../lib/format";

const NEW_WORKSPACE_ID = "__new__";
const RECENT_PROJECT_LIMIT = 4;

/**
 * The four pipeline stages Laqta runs on a local machine. They describe the
 * product flow, never a live job state — the honest runtime status lives in
 * the engine audit below.
 */
const PIPELINE_STAGES = [
  {
    id: "import",
    label: "Import",
    icon: FileVideo,
    copy: "The file is copied into your local data directory and probed with FFprobe.",
  },
  {
    id: "transcribe",
    label: "Transcribe",
    icon: Mic,
    copy: "Local speech recognition splits the audio into utterances at real pauses.",
  },
  {
    id: "rank",
    label: "Rank",
    icon: Gauge,
    copy: "Every candidate gets an explainable clip score that cites the transcript.",
  },
  {
    id: "render",
    label: "Render",
    icon: Clapperboard,
    copy: "The winners are cut to 1080×1920 with bilingual, RTL-aware captions.",
  },
];

interface DashboardHomeProps {
  projects: Project[];
  capabilities: CapabilitiesResponse | null;
  health: HealthResponse | null;
  /** Open a project in the studio editor. */
  onSelectProject: (projectId: string) => void;
  /** Open the "create project" dialog. */
  onOpenCreateModal: () => void;
  /** Switch to the full project library. */
  onOpenProjects: () => void;
  /** Import a dropped/selected file into a fresh workspace. */
  onDirectVideoDrop: (file: File) => Promise<void>;
  /** Create an empty workspace without opening the studio. */
  onCreateWorkspace: (name: string) => Promise<Project>;
  /** Search query owned by the Studio top header. */
  globalSearchQuery?: string;
}

/**
 * Dashboard landing screen.
 *
 * It is a home screen, not a second project list: it shows the fastest path
 * into the pipeline, the honest state of the local engines, real workspace
 * statistics and the most recently touched workspaces.
 */
export const DashboardHome: React.FC<DashboardHomeProps> = ({
  projects,
  capabilities,
  health,
  onSelectProject,
  onOpenCreateModal,
  onOpenProjects,
  onDirectVideoDrop,
  onCreateWorkspace,
  globalSearchQuery = "",
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isProcessingDrop, setIsProcessingDrop] = useState(false);
  const [isTargetModalOpen, setIsTargetModalOpen] = useState(false);
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [targetProjectId, setTargetProjectId] = useState<string | null>(null);
  const [isResolvingTarget, setIsResolvingTarget] = useState(false);
  const [targetError, setTargetError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ type: ToastType; message: string } | null>(null);

  const stats = useMemo(() => {
    let mediaCount = 0;
    let footageMs = 0;
    let diskBytes = 0;
    for (const project of projects) {
      for (const asset of project.media_assets ?? []) {
        mediaCount += 1;
        footageMs += asset.duration_ms || 0;
        diskBytes += asset.size_bytes || 0;
      }
    }
    return {
      workspaces: projects.length,
      mediaCount,
      footageMs,
      diskBytes,
      readyToEdit: projects.filter((p) => (p.media_count || p.media_assets?.length || 0) > 0)
        .length,
    };
  }, [projects]);

  const recentProjects = useMemo(() => {
    const query = globalSearchQuery.trim().toLowerCase();
    const matches = (project: Project) => {
      if (!query) return true;
      return (
        project.name.toLowerCase().includes(query) ||
        project.id.toLowerCase().includes(query) ||
        (project.media_assets ?? []).some((asset) =>
          asset.original_name.toLowerCase().includes(query),
        )
      );
    };
    return projects
      .filter(matches)
      .sort(
        (a, b) =>
          new Date(b.updated_at || b.created_at).getTime() -
          new Date(a.updated_at || a.created_at).getTime(),
      )
      .slice(0, RECENT_PROJECT_LIMIT);
  }, [projects, globalSearchQuery]);

  const urlIngestion = capabilities?.url_ingestion;
  const urlIngestionReady = Boolean(urlIngestion?.feature_flag && urlIngestion.yt_dlp.available);
  const ffmpegMissing = capabilities !== null && !capabilities.ffmpeg.available;

  const importFile = async (file: File) => {
    setIsProcessingDrop(true);
    try {
      await onDirectVideoDrop(file);
    } catch (err) {
      const message = err instanceof Error ? err.message : "The import could not be started.";
      setToast({ type: "error", message });
    } finally {
      setIsProcessingDrop(false);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) await importFile(file);
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) await importFile(file);
  };

  const openYouTubeImport = () => {
    setTargetError(null);
    if (projects.length === 0) {
      // No workspace yet: create one so the gated import has a destination.
      void resolveTarget(NEW_WORKSPACE_ID);
      return;
    }
    setIsTargetModalOpen(true);
  };

  const resolveTarget = async (selection: string) => {
    setIsResolvingTarget(true);
    setTargetError(null);
    try {
      let projectId = selection;
      if (selection === NEW_WORKSPACE_ID) {
        const created = await onCreateWorkspace("YouTube Import");
        projectId = created.id;
      }
      setTargetProjectId(projectId);
      setIsTargetModalOpen(false);
      setIsImportModalOpen(true);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "The workspace could not be prepared for the import.";
      setTargetError(message);
    } finally {
      setIsResolvingTarget(false);
    }
  };

  const statTiles = [
    {
      key: "workspaces",
      label: "Workspaces",
      value: String(stats.workspaces),
      hint: `${stats.readyToEdit} with media`,
      icon: FolderKanban,
      iconClass: "text-laqta-300",
    },
    {
      key: "media",
      label: "Media assets",
      value: String(stats.mediaCount),
      hint: stats.mediaCount === 1 ? "file imported" : "files imported",
      icon: Film,
      iconClass: "text-cyan-300",
    },
    {
      key: "footage",
      label: "Footage",
      value: formatDurationHuman(stats.footageMs),
      hint: "total imported",
      icon: Clock,
      iconClass: "text-emerald-300",
    },
    {
      key: "disk",
      label: "Local disk",
      value: formatBytes(stats.diskBytes),
      hint: "in your data dir",
      icon: HardDrive,
      iconClass: "text-amber-300",
    },
  ];

  return (
    <div className="mx-auto w-full max-w-[1500px] space-y-5" data-testid="dashboard-home">
      {toast && (
        <Toast
          type={toast.type}
          message={toast.message}
          onClose={() => setToast(null)}
          autoDismissMs={6000}
        />
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
        {/* 1. Hero: fastest path into the pipeline */}
        <section
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          aria-label="Import a video"
          data-testid="dashboard-hero"
          className={`laqta-card group relative flex flex-col overflow-hidden rounded-2xl p-6 transition-shadow duration-200 sm:p-8 xl:col-span-8 ${
            isDragging ? "shadow-[inset_0_0_0_2px_rgba(124,77,255,0.7)]" : ""
          }`}
        >
          {/* Decorative brand wash */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -top-28 -right-20 h-72 w-72 rounded-full bg-laqta-600/20 blur-3xl"
          />
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -bottom-32 left-1/3 h-64 w-64 rounded-full bg-cyan-500/10 blur-3xl"
          />

          <div className="relative z-10 flex h-full flex-col">
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-2.5 py-0.5 text-[10px] font-mono uppercase tracking-wider text-neon-cyan">
                <Lock className="h-3 w-3" aria-hidden="true" />
                127.0.0.1 · on-device
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-laqta-800/60 bg-laqta-950/60 px-2.5 py-0.5 text-[10px] font-mono tracking-wider text-laqta-200">
                <span dir="rtl">لقطّة</span>
                <span aria-hidden="true">·</span>
                <span>Laqta</span>
              </span>
              {health?.version && (
                <span className="rounded-full border border-slate-800 bg-obsidian-950/70 px-2.5 py-0.5 text-[10px] font-mono text-slate-400">
                  v{health.version}
                </span>
              )}
            </div>

            <h1 className="mt-4 max-w-2xl text-3xl font-black leading-[1.1] tracking-tight text-white sm:text-4xl">
              Cut long videos into <span className="laqta-gradient-text">vertical Shorts</span>
            </h1>
            <p className="mt-3 max-w-2xl text-sm leading-relaxed text-slate-400">
              Drop a podcast, stream or lecture here. Laqta transcribes it, proposes ranked clip
              candidates and renders 1080×1920 cuts with captions — entirely on this machine.
            </p>

            <div className="mt-6 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isProcessingDrop}
                className="laqta-gradient-surface inline-flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-semibold text-white shadow-laqta-glow transition-[filter,transform] duration-200 hover:brightness-110 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-300"
                data-testid="dashboard-upload-btn"
              >
                {isProcessingDrop ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <UploadCloud className="h-4 w-4" aria-hidden="true" />
                )}
                <span>{isProcessingDrop ? "Importing…" : "Upload Video"}</span>
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".mp4,.mov,.mkv,.webm,video/mp4,video/quicktime,video/x-matroska,video/webm"
                className="hidden"
                onChange={handleFileChange}
                data-testid="dashboard-file-input"
              />

              {urlIngestionReady ? (
                <button
                  type="button"
                  onClick={openYouTubeImport}
                  className="inline-flex items-center gap-2 rounded-xl border border-slate-700/60 bg-obsidian-950/70 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-laqta-500/60 hover:bg-laqta-950/40 hover:text-white cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
                  data-testid="dashboard-youtube-btn"
                >
                  <Youtube className="h-4 w-4 text-red-400" aria-hidden="true" />
                  <span>YouTube Link</span>
                </button>
              ) : (
                /* Fail-closed mirror of the project view: the button stays
                   visible but disabled with the exact reason. */
                <button
                  type="button"
                  disabled
                  aria-disabled="true"
                  title={
                    urlIngestion?.feature_flag
                      ? "yt-dlp is not installed on this machine. Install yt-dlp to enable YouTube import."
                      : "YouTube import is disabled on the backend (QATTA_ENABLE_URL_INGESTION=false). Imports still require yt-dlp and a rights confirmation."
                  }
                  className="inline-flex items-center gap-2 rounded-xl border border-slate-700/60 bg-obsidian-950/50 px-4 py-2.5 text-sm font-medium text-slate-500 cursor-not-allowed opacity-80"
                  data-testid="dashboard-youtube-btn-disabled"
                >
                  <Youtube className="h-4 w-4 text-red-400/70" aria-hidden="true" />
                  <span>YouTube Link</span>
                </button>
              )}

              <button
                type="button"
                onClick={onOpenCreateModal}
                className="inline-flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium text-slate-300 transition hover:bg-slate-800/70 hover:text-white cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
                data-testid="dashboard-new-project-btn"
              >
                <Plus className="h-4 w-4" aria-hidden="true" />
                <span>Empty workspace</span>
              </button>
            </div>

            <p className="mt-4 text-[11px] text-slate-500">
              MP4, MOV, MKV and WebM. The file is copied into your local data directory and never
              uploaded.
            </p>

            {ffmpegMissing && (
              <p
                role="status"
                className="mt-3 max-w-xl rounded-xl border border-amber-800/50 bg-amber-950/30 px-3 py-2 text-[11px] leading-relaxed text-amber-200"
              >
                FFmpeg was not found on this machine. Importing still works, but rendering and frame
                extraction will not.
              </p>
            )}

            {/* Drop hint + local-only promise — the whole card is the drop
                target, and nothing that is dropped ever leaves the device. */}
            <div className="mt-auto flex flex-wrap items-center justify-between gap-3 pt-6">
              <p className="text-[11px] text-slate-600">
                …or drag a video file anywhere onto this card.
              </p>
              <p className="inline-flex items-center gap-1.5 text-[11px] text-slate-500">
                <ShieldCheck className="h-3.5 w-3.5 text-neon-emerald" aria-hidden="true" />
                Media, audio and transcripts stay on this device.
              </p>
            </div>
          </div>

          {isDragging && (
            <div
              aria-hidden="true"
              className="pointer-events-none absolute inset-3 z-20 flex items-center justify-center rounded-xl border-2 border-dashed border-laqta-400/80 bg-obsidian-950/70 backdrop-blur-sm"
            >
              <span className="rounded-xl border border-laqta-500/50 bg-laqta-950/80 px-4 py-2 text-sm font-semibold text-laqta-100">
                Drop to import into a new workspace
              </span>
            </div>
          )}
        </section>

        {/* 2. Real workspace statistics */}
        <dl
          className="grid grid-cols-2 gap-3 xl:col-span-4 xl:grid-rows-2"
          data-testid="dashboard-stats"
        >
          {statTiles.map((tile) => {
            const Icon = tile.icon;
            return (
              <div
                key={tile.key}
                className="laqta-card flex flex-col justify-between rounded-2xl p-4 transition-colors duration-200 hover:border-laqta-500/40"
              >
                <dt className="flex items-center gap-1.5 text-[11px] font-medium text-slate-400">
                  <Icon className={`h-3.5 w-3.5 ${tile.iconClass}`} aria-hidden="true" />
                  {tile.label}
                </dt>
                <dd className="mt-2 text-2xl font-black tracking-tight text-white">{tile.value}</dd>
                <dd className="mt-0.5 text-[10px] text-slate-500">{tile.hint}</dd>
              </div>
            );
          })}
        </dl>
      </div>

      {/* 3. Honest engine audit */}
      <EngineStatusStrip capabilities={capabilities} />

      {/* 4. Continue where you left off */}
      {projects.length === 0 ? (
        <EmptyState onCreateProject={onOpenCreateModal} />
      ) : (
        <>
          <section className="space-y-3" aria-label="Recent workspaces">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Layers className="h-4 w-4 text-neon-cyan" aria-hidden="true" />
                <h2 className="text-sm font-bold text-white tracking-tight">
                  Continue where you left off
                </h2>
              </div>
              <button
                type="button"
                onClick={onOpenProjects}
                className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-slate-400 transition hover:text-white hover:bg-slate-800/70 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
                data-testid="dashboard-view-all-projects"
              >
                <span>View all workspaces</span>
                <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            </div>

            {recentProjects.length === 0 ? (
              <p className="rounded-2xl border border-dashed border-slate-800 bg-obsidian-900/40 px-4 py-6 text-center text-xs text-slate-500">
                No workspace matches “{globalSearchQuery.trim()}”.
              </p>
            ) : (
              <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
                {recentProjects.map((project) => {
                  const media = project.media_assets?.[0] ?? null;
                  return (
                    <li key={project.id}>
                      <div
                        role="button"
                        tabIndex={0}
                        onClick={() => onSelectProject(project.id)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            onSelectProject(project.id);
                          }
                        }}
                        className="group flex h-full cursor-pointer flex-col overflow-hidden rounded-2xl border border-slate-800/90 bg-obsidian-900/80 transition-all duration-200 hover:-translate-y-0.5 hover:border-laqta-500/50 hover:shadow-laqta-glow focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
                        data-testid={`dashboard-project-${project.id}`}
                      >
                        <div className="relative aspect-video w-full overflow-hidden border-b border-slate-800/80">
                          <ProjectPoster
                            mediaId={media?.id}
                            label={
                              media
                                ? `Preview frame of ${media.original_name}`
                                : `No preview frame for ${project.name}`
                            }
                            className="h-full w-full"
                          />
                          {media ? (
                            <span className="absolute bottom-1.5 right-1.5 rounded-md bg-black/70 px-1.5 py-0.5 font-mono text-[10px] text-white">
                              {formatDurationMs(media.duration_ms)}
                            </span>
                          ) : (
                            <span className="absolute bottom-1.5 left-1.5 rounded-md bg-black/70 px-1.5 py-0.5 text-[10px] text-slate-300">
                              No media yet
                            </span>
                          )}
                        </div>

                        <div className="flex flex-1 flex-col p-4">
                          <h3
                            dir="auto"
                            className="truncate text-sm font-bold text-white transition-colors group-hover:text-laqta-200"
                          >
                            {project.name}
                          </h3>
                          <p className="mt-1 text-[11px] text-slate-500">
                            Updated {formatRelativeTime(project.updated_at)}
                          </p>

                          {media ? (
                            <p className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[10px] text-slate-400">
                              <span className="inline-flex items-center gap-1">
                                <Video className="h-3 w-3 text-cyan-400" aria-hidden="true" />
                                {media.width}×{media.height}
                              </span>
                              <span aria-hidden="true">•</span>
                              <span className="uppercase">{media.video_codec}</span>
                              <span aria-hidden="true">•</span>
                              <span>{formatBytes(media.size_bytes)}</span>
                            </p>
                          ) : (
                            <p className="mt-2 text-[11px] text-slate-500">
                              Import a video to start the pipeline.
                            </p>
                          )}

                          <span className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-laqta-300 transition-transform group-hover:translate-x-1">
                            <span>Open workspace</span>
                            <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                          </span>
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          {/* 5. How the local pipeline works */}
          <section className="laqta-card rounded-2xl p-5" aria-label="How Laqta works">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm font-bold text-white tracking-tight">How Laqta works</h2>
              <span className="text-[10px] font-mono uppercase tracking-wider rounded-full bg-obsidian-950/80 border border-slate-800 px-2 py-0.5 text-slate-400">
                4 stages · all local
              </span>
            </div>

            <ol className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {PIPELINE_STAGES.map((stage, index) => {
                const Icon = stage.icon;
                return (
                  <li
                    key={stage.id}
                    className="rounded-xl border border-slate-800/80 bg-obsidian-950/50 p-3.5"
                  >
                    <div className="flex items-center gap-2">
                      <span className="inline-flex h-6 w-6 items-center justify-center rounded-md border border-laqta-700/60 bg-laqta-950/60 text-laqta-200">
                        <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                      </span>
                      <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-300">
                        {index + 1}. {stage.label}
                      </span>
                    </div>
                    <p className="mt-2 text-[11px] leading-relaxed text-slate-500">{stage.copy}</p>
                  </li>
                );
              })}
            </ol>
          </section>
        </>
      )}

      {/* 6. Gated YouTube import (PRD FR-12) */}
      <YouTubeTargetModal
        isOpen={isTargetModalOpen}
        projects={projects}
        onClose={() => setIsTargetModalOpen(false)}
        onResolveTarget={resolveTarget}
        isResolving={isResolvingTarget}
        error={targetError}
      />

      <YouTubeImportModal
        isOpen={isImportModalOpen}
        onClose={() => {
          setIsImportModalOpen(false);
          setTargetProjectId(null);
        }}
        projectId={targetProjectId ?? ""}
        onQueued={(_jobId) => {
          setIsImportModalOpen(false);
          setTargetProjectId(null);
          setToast({
            type: "info",
            message:
              "Import job queued — the video appears in its workspace as soon as the local download finishes.",
          });
        }}
      />
    </div>
  );
};

export default DashboardHome;
