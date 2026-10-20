import React, { useState, useMemo } from "react";
import {
  Folder,
  Plus,
  Trash2,
  ArrowRight,
  Video,
  Clock,
  Search,
  HardDrive,
  Film,
  LayoutGrid,
  List,
  Pencil,
  Copy,
  Info,
  Check,
  X,
  CheckSquare,
  Square,
} from "lucide-react";
import { Project } from "../../types/projects";
import { CapabilitiesResponse } from "../../types/capabilities";
import { HealthResponse } from "../../types/health";
import { ProjectPoster } from "../../components/studio/ProjectPoster";
import { Modal } from "../../components/ui/Modal";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { Button } from "../../components/ui/Button";
import { formatBytes, formatDurationHuman, formatDurationMs } from "../../lib/format";

interface ProjectListProps {
  projects: Project[];
  onSelectProject: (projectId: string) => void;
  onOpenCreateModal: () => void;
  onDeleteProject: (projectId: string) => Promise<void>;
  onRenameProject?: (projectId: string, newName: string) => Promise<void>;
  onDuplicateProject?: (projectId: string) => Promise<void>;
  capabilities?: CapabilitiesResponse | null;
  health?: HealthResponse | null;
  /**
   * Search query owned by the Studio top header; combined with the local
   * filter-bar search so both inputs filter the same list.
   */
  globalSearchQuery?: string;
  onClearGlobalSearch?: () => void;
}

type SortOption = "newest" | "oldest" | "name_asc" | "name_desc" | "duration" | "size";
type StatusFilter = "all" | "with_media" | "drafts";

export const ProjectList: React.FC<ProjectListProps> = ({
  projects,
  onSelectProject,
  onOpenCreateModal,
  onDeleteProject,
  onRenameProject,
  onDuplicateProject,
  capabilities,
  health,
  globalSearchQuery = "",
  onClearGlobalSearch,
}) => {
  const [searchQuery, setSearchQuery] = useState("");
  const [sortBy, setSortBy] = useState<SortOption>("newest");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [viewMode, setViewMode] = useState<"grid" | "table">("grid");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // Inline renaming state
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");
  const [isRenaming, setIsRenaming] = useState(false);

  // Duplication state
  const [duplicatingId, setDuplicatingId] = useState<string | null>(null);

  // Info modal state
  const [infoProject, setInfoProject] = useState<Project | null>(null);

  // Batch delete state
  const [isConfirmingDeletion, setIsConfirmingDeletion] = useState(false);

  // Shared confirmation dialog state (single & batch project deletion).
  const [confirmState, setConfirmState] = useState<{
    title: string;
    message: string;
    onConfirm: () => Promise<void> | void;
  } | null>(null);

  const totalVideos = useMemo(() => {
    return projects.reduce((acc, p) => acc + (p.media_count || p.media_assets?.length || 0), 0);
  }, [projects]);

  const totalSizeBytes = useMemo(() => {
    return projects.reduce((acc, p) => {
      const mediaSize = p.media_assets?.reduce((mAcc, m) => mAcc + (m.size_bytes || 0), 0) || 0;
      return acc + mediaSize;
    }, 0);
  }, [projects]);

  const totalDurationMs = useMemo(() => {
    return projects.reduce((acc, p) => {
      const primary = p.media_assets?.[0];
      return acc + (primary?.duration_ms || 0);
    }, 0);
  }, [projects]);

  const filterCounts = useMemo(() => {
    const withMedia = projects.filter(
      (p) => (p.media_count || p.media_assets?.length || 0) > 0,
    ).length;
    const drafts = projects.filter(
      (p) => (p.media_count || p.media_assets?.length || 0) === 0,
    ).length;
    return {
      all: projects.length,
      with_media: withMedia,
      drafts,
    };
  }, [projects]);

  /** True when the project matches one lowercase search term. */
  const matchesQuery = (project: Project, q: string): boolean => {
    return (
      project.name.toLowerCase().includes(q) ||
      project.id.toLowerCase().includes(q) ||
      project.media_assets.some(
        (m) => m.original_name.toLowerCase().includes(q) || m.video_codec.toLowerCase().includes(q),
      )
    );
  };

  const filteredProjects = useMemo(() => {
    let result = [...projects];

    // Status filter
    if (statusFilter === "with_media") {
      result = result.filter((p) => (p.media_count || p.media_assets?.length || 0) > 0);
    } else if (statusFilter === "drafts") {
      result = result.filter((p) => (p.media_count || p.media_assets?.length || 0) === 0);
    }

    // Search: header (global) query AND local filter-bar query must both match
    const queries = [globalSearchQuery, searchQuery]
      .map((q) => q.toLowerCase().trim())
      .filter(Boolean);
    if (queries.length > 0) {
      result = result.filter((p) => queries.every((q) => matchesQuery(p, q)));
    }

    // Sort order
    if (sortBy === "newest") {
      result.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
    } else if (sortBy === "oldest") {
      result.sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
    } else if (sortBy === "name_asc") {
      result.sort((a, b) => a.name.localeCompare(b.name));
    } else if (sortBy === "name_desc") {
      result.sort((a, b) => b.name.localeCompare(a.name));
    } else if (sortBy === "duration") {
      result.sort((a, b) => {
        const durA = a.media_assets?.[0]?.duration_ms || 0;
        const durB = b.media_assets?.[0]?.duration_ms || 0;
        return durB - durA;
      });
    } else if (sortBy === "size") {
      result.sort((a, b) => {
        const sizeA = a.media_assets?.[0]?.size_bytes || 0;
        const sizeB = b.media_assets?.[0]?.size_bytes || 0;
        return sizeB - sizeA;
      });
    }

    return result;
  }, [projects, searchQuery, globalSearchQuery, sortBy, statusFilter]);

  // Batch selection handlers
  const isAllSelected = useMemo(() => {
    return filteredProjects.length > 0 && filteredProjects.every((p) => selectedIds.has(p.id));
  }, [filteredProjects, selectedIds]);

  const toggleSelectAll = () => {
    if (isAllSelected) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filteredProjects.map((p) => p.id)));
    }
  };

  const toggleSelectOne = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const confirmBatchDelete = () => {
    if (selectedIds.size === 0) return;
    const count = selectedIds.size;
    setConfirmState({
      title: `Delete ${count} selected project${count > 1 ? "s" : ""}?`,
      message: `All media files for ${count} project${count > 1 ? "s" : ""} will be permanently removed from local disk. This action cannot be undone.`,
      onConfirm: async () => {
        setIsConfirmingDeletion(true);
        try {
          for (const id of Array.from(selectedIds)) {
            await onDeleteProject(id);
          }
          setSelectedIds(new Set());
        } finally {
          setIsConfirmingDeletion(false);
          setConfirmState(null);
        }
      },
    });
  };

  /** Single-project delete confirmation (grid + table views). */
  const confirmDeleteProject = (project: Project) => {
    setConfirmState({
      title: `Delete "${project.name}"?`,
      message:
        "The project and all associated local media files will be permanently removed. This action cannot be undone.",
      onConfirm: async () => {
        await onDeleteProject(project.id);
        setConfirmState(null);
      },
    });
  };

  // Inline rename handlers
  const handleStartRename = (e: React.MouseEvent, project: Project) => {
    e.stopPropagation();
    setEditingProjectId(project.id);
    setEditingName(project.name);
  };

  const handleSaveRename = async (projectId: string) => {
    const trimmed = editingName.trim();
    if (!trimmed || !onRenameProject) {
      setEditingProjectId(null);
      return;
    }

    setIsRenaming(true);
    try {
      await onRenameProject(projectId, trimmed);
      setEditingProjectId(null);
    } finally {
      setIsRenaming(false);
    }
  };

  const handleCancelRename = (e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    setEditingProjectId(null);
    setEditingName("");
  };

  // Duplicate handler
  const handleDuplicate = async (e: React.MouseEvent, projectId: string) => {
    e.stopPropagation();
    if (!onDuplicateProject) return;
    setDuplicatingId(projectId);
    try {
      await onDuplicateProject(projectId);
    } finally {
      setDuplicatingId(null);
    }
  };

  return (
    <div className="mx-auto w-full max-w-[1500px] space-y-6" data-testid="project-list-view">
      {/* 1. Library banner */}
      <div className="bg-gradient-to-r from-obsidian-900/90 via-purple-950/20 to-obsidian-900/90 border border-slate-800/90 rounded-2xl p-6 backdrop-blur-md shadow-xl flex flex-col md:flex-row md:items-center justify-between gap-5">
        <div className="space-y-2">
          <div className="flex items-center space-x-2.5">
            <div className="p-2.5 bg-purple-600/20 border border-purple-500/30 rounded-xl text-laqta-400">
              <Folder className="h-5 w-5" />
            </div>
            <h1 className="text-xl font-black text-white tracking-tight">My Projects</h1>
            <span className="text-xs font-mono font-semibold px-2.5 py-0.5 rounded-full bg-purple-900/50 border border-purple-700/40 text-laqta-200">
              {projects.length} {projects.length === 1 ? "Workspace" : "Workspaces"}
            </span>
            {health?.version && (
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-obsidian-950/80 border border-slate-800 text-slate-400">
                v{health.version}
              </span>
            )}
          </div>
          <p className="text-xs text-slate-400 max-w-xl">
            Manage your local video projects, imported footage, and Shorts workspaces. Media and
            transcripts stay on this machine; optional cloud APIs stay off unless you explicitly
            enable them.
          </p>

          {/* Quick Stats Pills */}
          <div className="flex items-center flex-wrap gap-2 pt-1 text-[11px] font-mono">
            <span className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-lg bg-obsidian-950/80 border border-slate-800 text-slate-300">
              <Film className="h-3 w-3 text-indigo-400" />
              <span>
                {totalVideos} {totalVideos === 1 ? "video" : "videos"}
              </span>
            </span>
            <span className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-lg bg-obsidian-950/80 border border-slate-800 text-slate-300">
              <Clock className="h-3 w-3 text-cyan-400" />
              <span>{formatDurationHuman(totalDurationMs)} footage</span>
            </span>
            <span className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-lg bg-obsidian-950/80 border border-slate-800 text-slate-300">
              <HardDrive className="h-3 w-3 text-laqta-400" />
              <span>{formatBytes(totalSizeBytes)} local disk</span>
            </span>
          </div>
        </div>

        <div className="flex items-center space-x-3 shrink-0">
          <button
            onClick={onOpenCreateModal}
            className="inline-flex items-center space-x-2 px-4 py-2.5 bg-gradient-to-r from-laqta-600 via-purple-600 to-indigo-600 hover:from-laqta-500 hover:to-indigo-500 text-white text-xs font-semibold rounded-xl shadow-lg shadow-laqta-600/20 active:scale-95 transition-all cursor-pointer"
          >
            <Plus className="h-4 w-4" />
            <span>Create New Project</span>
          </button>
        </div>
      </div>

      {/* 2. Controls & Filter Bar */}
      <div className="space-y-3 pt-1">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          {/* Section Heading & Filter Tabs */}
          <div className="flex items-center flex-wrap gap-2 sm:gap-3">
            <h2 className="text-base font-bold text-white tracking-tight mr-1">Your Projects</h2>

            {/* Status Filter Chips */}
            <div className="inline-flex p-0.5 rounded-xl bg-obsidian-950 border border-slate-800 text-xs">
              <button
                onClick={() => setStatusFilter("all")}
                aria-pressed={statusFilter === "all"}
                className={`px-3 py-1 rounded-lg font-medium transition cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 ${
                  statusFilter === "all"
                    ? "bg-purple-900/60 text-white font-semibold shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                All ({filterCounts.all})
              </button>
              <button
                onClick={() => setStatusFilter("with_media")}
                aria-pressed={statusFilter === "with_media"}
                className={`px-3 py-1 rounded-lg font-medium transition cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 ${
                  statusFilter === "with_media"
                    ? "bg-purple-900/60 text-white font-semibold shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                With Video ({filterCounts.with_media})
              </button>
              <button
                onClick={() => setStatusFilter("drafts")}
                aria-pressed={statusFilter === "drafts"}
                className={`px-3 py-1 rounded-lg font-medium transition cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 ${
                  statusFilter === "drafts"
                    ? "bg-purple-900/60 text-white font-semibold shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Drafts ({filterCounts.drafts})
              </button>
            </div>
          </div>

          {/* Right Tools: Search, Sort, View Mode */}
          <div className="flex items-center flex-wrap gap-2.5">
            {/* Search Input */}
            <div className="relative w-full sm:w-56">
              <Search className="h-3.5 w-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search projects, files..."
                aria-label="Search projects and files"
                className="w-full pl-8 pr-3 py-1.5 rounded-xl bg-obsidian-950 border border-slate-800 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-laqta-500/60 focus:ring-1 focus:ring-purple-500/40 transition"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery("")}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 rounded"
                  aria-label="Clear search"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </div>

            {/* Sort Dropdown */}
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortOption)}
              aria-label="Sort projects"
              className="px-2.5 py-1.5 rounded-xl bg-obsidian-950 border border-slate-800 text-xs text-slate-300 focus:outline-none focus:border-laqta-500/60 focus:ring-1 focus:ring-purple-500/40 cursor-pointer"
            >
              <option value="newest">Newest Created</option>
              <option value="oldest">Oldest Created</option>
              <option value="name_asc">Name (A → Z)</option>
              <option value="name_desc">Name (Z → A)</option>
              <option value="duration">Video Duration</option>
              <option value="size">File Size</option>
            </select>

            {/* View Mode Toggle: Grid vs Table */}
            <div className="inline-flex p-0.5 rounded-xl bg-obsidian-950 border border-slate-800">
              <button
                onClick={() => setViewMode("grid")}
                aria-pressed={viewMode === "grid"}
                className={`p-1.5 rounded-lg transition cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 ${
                  viewMode === "grid"
                    ? "bg-purple-900/60 text-white"
                    : "text-slate-400 hover:text-slate-200"
                }`}
                title="Grid Cards View"
                aria-label="Grid Cards View"
              >
                <LayoutGrid className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => setViewMode("table")}
                aria-pressed={viewMode === "table"}
                className={`p-1.5 rounded-lg transition cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 ${
                  viewMode === "table"
                    ? "bg-purple-900/60 text-white"
                    : "text-slate-400 hover:text-slate-200"
                }`}
                title="Table List View"
                aria-label="Table List View"
              >
                <List className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </div>

        {/* 3. Batch Action Bar (when projects are selected) */}
        {selectedIds.size > 0 && (
          <div className="flex items-center justify-between px-4 py-2.5 rounded-xl bg-purple-950/70 border border-purple-800/60 shadow-lg backdrop-blur-md animate-in fade-in duration-200">
            <div className="flex items-center space-x-2 text-xs text-laqta-100 font-medium">
              <CheckSquare className="h-4 w-4 text-laqta-300" />
              <span>
                {selectedIds.size} {selectedIds.size === 1 ? "project" : "projects"} selected
              </span>
            </div>

            <div className="flex items-center space-x-2">
              <button
                onClick={confirmBatchDelete}
                disabled={isConfirmingDeletion}
                className="inline-flex items-center space-x-1 px-3 py-1 rounded-lg bg-red-950/60 hover:bg-red-900/80 border border-red-800/60 text-red-300 text-xs font-medium transition cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500 disabled:opacity-50"
              >
                <Trash2 className="h-3.5 w-3.5" />
                <span>{isConfirmingDeletion ? "Deleting..." : "Delete Selected"}</span>
              </button>
              <button
                onClick={() => setSelectedIds(new Set())}
                className="px-2.5 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 text-xs font-medium transition cursor-pointer"
              >
                Deselect All
              </button>
            </div>
          </div>
        )}
      </div>

      {/* 4. Projects View: Grid or Table */}
      {filteredProjects.length > 0 ? (
        viewMode === "grid" ? (
          /* Grid View */
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4.5">
            {filteredProjects.map((proj) => {
              const primaryMedia = proj.media_assets.length > 0 ? proj.media_assets[0] : null;
              const isSelected = selectedIds.has(proj.id);
              const isEditingThis = editingProjectId === proj.id;

              return (
                <div
                  key={proj.id}
                  onClick={() => onSelectProject(proj.id)}
                  className={`group relative bg-obsidian-900/80 hover:bg-slate-900/90 border rounded-2xl p-5 transition-all duration-200 shadow-lg flex flex-col justify-between cursor-pointer overflow-hidden backdrop-blur-sm ${
                    isSelected
                      ? "border-purple-500 bg-purple-950/20 shadow-purple-950/30"
                      : "border-slate-800/90 hover:border-purple-500/50 hover:shadow-purple-950/20"
                  }`}
                >
                  {/* Subtle top glow highlight on hover */}
                  <div className="absolute inset-x-0 top-0 h-0.5 bg-gradient-to-r from-transparent via-purple-500/0 group-hover:via-purple-500/50 to-transparent transition-all"></div>

                  <div>
                    {/* Top Row: Selection Checkbox, Folder Icon, and Actions */}
                    <div className="flex items-start justify-between">
                      <div className="flex items-center space-x-2.5">
                        <button
                          onClick={(e) => toggleSelectOne(e, proj.id)}
                          className="p-1 rounded text-slate-500 hover:text-laqta-300 transition"
                          aria-label={isSelected ? "Deselect" : "Select"}
                        >
                          {isSelected ? (
                            <CheckSquare className="h-4 w-4 text-laqta-300" />
                          ) : (
                            <Square className="h-4 w-4" />
                          )}
                        </button>
                        <div className="p-2 bg-obsidian-950 border border-slate-800 rounded-xl text-laqta-400 group-hover:scale-105 group-hover:text-laqta-300 transition-all shadow-sm">
                          <Folder className="h-4 w-4" />
                        </div>
                      </div>

                      {/* Quick Action Icons */}
                      <div
                        className="flex items-center space-x-1"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {/* Rename Action */}
                        {onRenameProject && (
                          <button
                            onClick={(e) => handleStartRename(e, proj)}
                            className="text-slate-500 hover:text-laqta-200 p-1.5 rounded-lg hover:bg-slate-800/80 transition-colors"
                            title="Rename Project"
                            aria-label={`Rename project ${proj.name}`}
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                        )}

                        {/* Duplicate Action */}
                        {onDuplicateProject && (
                          <button
                            onClick={(e) => handleDuplicate(e, proj.id)}
                            disabled={duplicatingId === proj.id}
                            className="text-slate-500 hover:text-cyan-300 p-1.5 rounded-lg hover:bg-slate-800/80 transition-colors disabled:opacity-50"
                            title="Duplicate Project"
                            aria-label={`Duplicate project ${proj.name}`}
                          >
                            <Copy className="h-3.5 w-3.5" />
                          </button>
                        )}

                        {/* Info Action */}
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setInfoProject(proj);
                          }}
                          className="text-slate-500 hover:text-indigo-300 p-1.5 rounded-lg hover:bg-slate-800/80 transition-colors"
                          title="Project Info"
                          aria-label={`Project info for ${proj.name}`}
                        >
                          <Info className="h-3.5 w-3.5" />
                        </button>

                        {/* Delete Action */}
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            confirmDeleteProject(proj);
                          }}
                          className="text-slate-500 hover:text-red-400 p-1.5 rounded-lg hover:bg-red-950/30 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
                          aria-label={`Delete project ${proj.name}`}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>

                    {/* Project Name (Editable or Display) */}
                    {isEditingThis ? (
                      <div
                        className="mt-3 flex items-center space-x-1.5"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <input
                          type="text"
                          value={editingName}
                          onChange={(e) => setEditingName(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") handleSaveRename(proj.id);
                            if (e.key === "Escape") handleCancelRename();
                          }}
                          autoFocus
                          dir="auto"
                          className="w-full px-2.5 py-1 rounded-lg bg-obsidian-950 border border-purple-500 text-xs font-bold text-white focus:outline-none"
                        />
                        <button
                          onClick={() => handleSaveRename(proj.id)}
                          disabled={isRenaming || !editingName.trim()}
                          className="p-1.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs disabled:opacity-50 cursor-pointer"
                          title="Save Name"
                        >
                          <Check className="h-3.5 w-3.5" />
                        </button>
                        <button
                          onClick={handleCancelRename}
                          className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs cursor-pointer"
                          title="Cancel"
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ) : (
                      <h3
                        dir="auto"
                        className="text-sm font-bold text-white mt-3.5 group-hover:text-laqta-300 transition-colors line-clamp-1"
                      >
                        {proj.name}
                      </h3>
                    )}

                    <div className="flex items-center space-x-2 text-[11px] text-slate-400 mt-1 font-mono">
                      <span>Created {new Date(proj.created_at).toLocaleDateString()}</span>
                      {primaryMedia && (
                        <>
                          <span>•</span>
                          <span className="text-slate-500">
                            {formatBytes(primaryMedia.size_bytes)}
                          </span>
                        </>
                      )}
                    </div>

                    {/* Primary Media Preview — real frame streamed locally */}
                    {primaryMedia ? (
                      <div className="mt-3.5 space-y-2">
                        <div className="relative aspect-video w-full overflow-hidden rounded-xl border border-slate-800/90 bg-obsidian-950">
                          <ProjectPoster
                            mediaId={primaryMedia.id}
                            label={`Preview frame of ${primaryMedia.original_name}`}
                            className="h-full w-full"
                          />
                          <span className="absolute bottom-1.5 right-1.5 rounded-md bg-black/70 px-1.5 py-0.5 font-mono text-[10px] text-white">
                            {formatDurationMs(primaryMedia.duration_ms)}
                          </span>
                        </div>

                        <div className="flex items-center space-x-2 text-xs text-slate-200">
                          <Video className="h-3.5 w-3.5 text-indigo-400 shrink-0" />
                          <span dir="auto" className="truncate font-medium text-slate-300">
                            {primaryMedia.original_name}
                          </span>
                        </div>

                        <div className="flex items-center flex-wrap gap-x-2 gap-y-1 text-[11px] text-slate-400 font-mono">
                          <span className="text-slate-300">
                            {primaryMedia.width}×{primaryMedia.height}
                          </span>
                          <span>•</span>
                          <span className="uppercase font-semibold text-slate-400">
                            {primaryMedia.video_codec}
                          </span>
                        </div>
                      </div>
                    ) : (
                      <div className="mt-3.5 p-3 bg-obsidian-950/40 border border-dashed border-slate-800/60 rounded-xl text-xs text-slate-500 flex items-center space-x-2">
                        <Film className="h-3.5 w-3.5 text-slate-600" />
                        <span>No media imported yet</span>
                      </div>
                    )}
                  </div>

                  {/* Footer Action Bar */}
                  <div className="mt-4 pt-3 border-t border-slate-800/70 flex items-center justify-between text-xs text-slate-400">
                    <span className="font-medium">
                      {proj.media_count} {proj.media_count === 1 ? "video" : "videos"}
                    </span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectProject(proj.id);
                      }}
                      className="inline-flex items-center space-x-1 text-laqta-400 font-medium group-hover:translate-x-1 transition-transform rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 px-1 -mr-1 cursor-pointer"
                      aria-label={`Open project ${proj.name}`}
                    >
                      <span>Open</span>
                      <ArrowRight className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          /* Table View */
          <div className="bg-obsidian-900/80 border border-slate-800/90 rounded-2xl overflow-hidden backdrop-blur-md shadow-lg">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="border-b border-slate-800/80 bg-obsidian-950/90 text-slate-400 font-medium font-mono text-[11px]">
                    <th className="py-3 px-4 w-10">
                      <button
                        onClick={toggleSelectAll}
                        className="p-1 rounded text-slate-400 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
                        aria-label={isAllSelected ? "Deselect all projects" : "Select all projects"}
                      >
                        {isAllSelected ? (
                          <CheckSquare className="h-4 w-4 text-laqta-300" />
                        ) : (
                          <Square className="h-4 w-4" />
                        )}
                      </button>
                    </th>
                    <th className="py-3 px-4">Project Name</th>
                    <th className="py-3 px-4">Video Asset</th>
                    <th className="py-3 px-4">Duration</th>
                    <th className="py-3 px-4">Resolution</th>
                    <th className="py-3 px-4">Size</th>
                    <th className="py-3 px-4">Created Date</th>
                    <th className="py-3 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {filteredProjects.map((proj) => {
                    const primary = proj.media_assets?.[0];
                    const isSelected = selectedIds.has(proj.id);
                    const isEditingThis = editingProjectId === proj.id;

                    return (
                      <tr
                        key={proj.id}
                        onClick={() => onSelectProject(proj.id)}
                        className={`hover:bg-slate-900/70 transition cursor-pointer ${
                          isSelected ? "bg-purple-950/20" : ""
                        }`}
                      >
                        {/* Select Checkbox */}
                        <td className="py-3.5 px-4" onClick={(e) => e.stopPropagation()}>
                          <button
                            onClick={(e) => toggleSelectOne(e, proj.id)}
                            className="p-1 rounded text-slate-500 hover:text-laqta-300 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
                            aria-label={
                              isSelected ? `Deselect ${proj.name}` : `Select ${proj.name}`
                            }
                          >
                            {isSelected ? (
                              <CheckSquare className="h-4 w-4 text-laqta-300" />
                            ) : (
                              <Square className="h-4 w-4" />
                            )}
                          </button>
                        </td>

                        {/* Project Name (Editable or Static) */}
                        <td className="py-3.5 px-4 font-semibold text-white">
                          {isEditingThis ? (
                            <div
                              className="flex items-center space-x-1.5"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <input
                                type="text"
                                value={editingName}
                                onChange={(e) => setEditingName(e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") handleSaveRename(proj.id);
                                  if (e.key === "Escape") handleCancelRename();
                                }}
                                autoFocus
                                dir="auto"
                                className="px-2 py-1 rounded bg-obsidian-950 border border-purple-500 text-xs font-bold text-white focus:outline-none"
                              />
                              <button
                                onClick={() => handleSaveRename(proj.id)}
                                disabled={isRenaming || !editingName.trim()}
                                className="p-1 rounded bg-purple-600 hover:bg-purple-500 text-white"
                              >
                                <Check className="h-3 w-3" />
                              </button>
                              <button
                                onClick={handleCancelRename}
                                className="p-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300"
                              >
                                <X className="h-3 w-3" />
                              </button>
                            </div>
                          ) : (
                            <div className="flex items-center space-x-2">
                              <Folder className="h-4 w-4 text-laqta-400 shrink-0" />
                              <button
                                onClick={() => onSelectProject(proj.id)}
                                className="text-left hover:text-laqta-300 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 rounded cursor-pointer"
                                aria-label={`Open project ${proj.name}`}
                              >
                                <span dir="auto" className="truncate max-w-xs block">
                                  {proj.name}
                                </span>
                              </button>
                            </div>
                          )}
                        </td>

                        {/* Video Media Asset */}
                        <td className="py-3.5 px-4 text-slate-300 font-mono text-[11px]">
                          {primary ? (
                            <div className="flex items-center space-x-2 max-w-xs">
                              <ProjectPoster
                                mediaId={primary.id}
                                label={`Preview frame of ${primary.original_name}`}
                                className="h-8 w-14 shrink-0 rounded-md border border-slate-800"
                              />
                              <span dir="auto" className="truncate">
                                {primary.original_name}
                              </span>
                            </div>
                          ) : (
                            <span className="text-slate-500 italic">No media</span>
                          )}
                        </td>

                        {/* Duration */}
                        <td className="py-3.5 px-4 font-mono text-slate-300">
                          {primary ? formatDurationMs(primary.duration_ms) : "—"}
                        </td>

                        {/* Resolution */}
                        <td className="py-3.5 px-4 font-mono text-slate-300">
                          {primary ? `${primary.width}×${primary.height}` : "—"}
                        </td>

                        {/* Size */}
                        <td className="py-3.5 px-4 font-mono text-slate-400">
                          {primary ? formatBytes(primary.size_bytes) : "—"}
                        </td>

                        {/* Created Date */}
                        <td className="py-3.5 px-4 text-slate-400 font-mono text-[11px]">
                          {new Date(proj.created_at).toLocaleDateString()}
                        </td>

                        {/* Actions */}
                        <td className="py-3.5 px-4 text-right" onClick={(e) => e.stopPropagation()}>
                          <div className="inline-flex items-center space-x-1">
                            {onRenameProject && (
                              <button
                                onClick={(e) => handleStartRename(e, proj)}
                                className="p-1.5 text-slate-400 hover:text-laqta-200 hover:bg-slate-800 rounded transition"
                                title="Rename"
                              >
                                <Pencil className="h-3.5 w-3.5" />
                              </button>
                            )}
                            {onDuplicateProject && (
                              <button
                                onClick={(e) => handleDuplicate(e, proj.id)}
                                disabled={duplicatingId === proj.id}
                                className="p-1.5 text-slate-400 hover:text-cyan-300 hover:bg-slate-800 rounded transition disabled:opacity-50"
                                title="Duplicate"
                              >
                                <Copy className="h-3.5 w-3.5" />
                              </button>
                            )}
                            <button
                              onClick={() => setInfoProject(proj)}
                              className="p-1.5 text-slate-400 hover:text-indigo-300 hover:bg-slate-800 rounded transition"
                              title="Info"
                            >
                              <Info className="h-3.5 w-3.5" />
                            </button>
                            <button
                              onClick={() => confirmDeleteProject(proj)}
                              className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-red-950/30 rounded transition focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
                              title="Delete"
                              aria-label={`Delete project ${proj.name}`}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )
      ) : (
        /* Empty Search or Filter Results */
        <div className="py-12 text-center rounded-2xl bg-obsidian-900/40 border border-dashed border-slate-800 space-y-3">
          <p className="text-sm font-medium text-slate-300">
            {searchQuery
              ? `No projects found matching "${searchQuery}"`
              : "No projects match the selected filter."}
          </p>
          <button
            onClick={() => {
              setSearchQuery("");
              setStatusFilter("all");
              onClearGlobalSearch?.();
            }}
            className="text-xs text-laqta-400 hover:text-laqta-300 underline font-medium cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 rounded"
          >
            Clear Filters
          </button>
        </div>
      )}

      {/* 5. Project Metadata Details Modal */}
      <Modal
        isOpen={Boolean(infoProject)}
        onClose={() => setInfoProject(null)}
        title={infoProject?.name ?? ""}
        maxWidthClass="max-w-lg"
      >
        {infoProject && (
          <div className="space-y-5">
            <div className="flex items-center space-x-2.5">
              <div className="p-2 bg-purple-950/60 border border-purple-800/40 rounded-xl text-laqta-400">
                <Folder className="h-4 w-4" />
              </div>
              <p className="text-[11px] font-mono text-slate-400">ID: {infoProject.id}</p>
            </div>

            {/* Metadata Fields */}
            <div className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-3 p-3 bg-obsidian-950 rounded-xl border border-slate-800/80 font-mono text-[11px]">
                <div>
                  <span className="text-slate-500 block">Created At</span>
                  <span className="text-slate-300 font-medium">
                    {new Date(infoProject.created_at).toLocaleString()}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500 block">Last Updated</span>
                  <span className="text-slate-300 font-medium">
                    {new Date(infoProject.updated_at).toLocaleString()}
                  </span>
                </div>
              </div>

              {/* Media Asset specs */}
              {infoProject.media_assets?.length > 0 ? (
                <div className="p-3 bg-obsidian-950 rounded-xl border border-slate-800/80 space-y-2 font-mono text-[11px]">
                  <span className="text-xs font-semibold text-slate-200 block font-sans">
                    Primary Media Specification
                  </span>
                  <div className="grid grid-cols-2 gap-2 text-slate-300">
                    <div>
                      <span className="text-slate-500 block">Filename</span>
                      <span dir="auto" className="truncate block font-medium">
                        {infoProject.media_assets[0].original_name}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block">Duration</span>
                      <span className="font-medium">
                        {formatDurationMs(infoProject.media_assets[0].duration_ms)} (
                        {Math.round(infoProject.media_assets[0].duration_ms / 1000)}s)
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block">Resolution</span>
                      <span className="font-medium">
                        {infoProject.media_assets[0].width}×{infoProject.media_assets[0].height}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block">Codecs</span>
                      <span className="font-medium uppercase">
                        {infoProject.media_assets[0].video_codec} /{" "}
                        {infoProject.media_assets[0].audio_codec}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block">File Size</span>
                      <span className="font-medium">
                        {formatBytes(infoProject.media_assets[0].size_bytes)}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block">Storage Path</span>
                      <span className="truncate block text-slate-400 text-[10px]">
                        {capabilities?.storage.data_dir || "local data dir"}/{infoProject.id}/
                      </span>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="p-3 bg-obsidian-950/60 rounded-xl border border-slate-800/60 text-slate-500 text-center">
                  No video has been imported into this project yet.
                </div>
              )}
            </div>

            {/* Modal Actions */}
            <div className="flex items-center justify-end space-x-2 pt-2">
              <Button variant="secondary" size="sm" onClick={() => setInfoProject(null)}>
                Close
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => {
                  const id = infoProject.id;
                  setInfoProject(null);
                  onSelectProject(id);
                }}
              >
                Open in Studio
                <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
              </Button>
            </div>
          </div>
        )}
      </Modal>

      {/* 6. Shared Deletion Confirmation (single + batch) */}
      <ConfirmDialog
        isOpen={Boolean(confirmState)}
        title={confirmState?.title ?? ""}
        message={confirmState?.message ?? ""}
        confirmLabel="Delete Project"
        isDestructive
        isConfirming={isConfirmingDeletion}
        onClose={() => setConfirmState(null)}
        onConfirm={() => {
          void confirmState?.onConfirm();
        }}
      />
    </div>
  );
};

export default ProjectList;
