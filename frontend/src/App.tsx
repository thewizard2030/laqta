import React, { useEffect, useState, useCallback } from "react";
import { StudioLayout } from "./components/studio/StudioLayout";
import { ErrorBoundary } from "./components/ui/ErrorBoundary";
import { StudioNavTab } from "./components/studio/StudioSidebar";
import { PrivacyBanner } from "./components/PrivacyBanner";
import { CapabilitiesCard } from "./components/CapabilitiesCard";
import { EmptyState } from "./components/EmptyState";
import { ErrorMessage } from "./components/ErrorMessage";
import { LoadingSkeleton } from "./components/LoadingSkeleton";
import { CreateProjectModal } from "./features/projects/CreateProjectModal";
import { ProjectDetailView } from "./features/projects/ProjectDetailView";
import { ProjectList } from "./features/projects/ProjectList";
import { DashboardHome } from "./features/dashboard/DashboardHome";
import { Toast, ToastType } from "./components/ui/Toast";
import { api, ApiClientError } from "./lib/api/client";
import { CapabilitiesResponse } from "./types/capabilities";
import { HealthResponse } from "./types/health";
import { Project } from "./types/projects";

export const App: React.FC = () => {
  const [capabilities, setCapabilities] = useState<CapabilitiesResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<StudioNavTab>("dashboard");
  // Tab the user came from when opening a workspace; used by the "back"
  // action so the studio editor returns to the list it was opened from.
  const [returnTab, setReturnTab] = useState<StudioNavTab>("dashboard");
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isError, setIsError] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [isRetrying, setIsRetrying] = useState(false);
  // Non-blocking feedback for dashboard-level actions (import failures, …).
  const [toast, setToast] = useState<{ type: ToastType; message: string } | null>(null);
  // Header search query; passed into the studio layout and used to filter lists.
  const [globalSearchQuery, setGlobalSearchQuery] = useState("");

  // Ctrl+K / Cmd+K focuses the studio search field (advertised by the ⌘K badge).
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        document.querySelector<HTMLInputElement>('[data-testid="studio-search-input"]')?.focus();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const fetchAppData = useCallback(async () => {
    setIsError(false);
    setErrorMessage("");

    try {
      // Parallel fetch for health, capabilities, and projects list
      const [healthData, capabilitiesData, projectsData] = await Promise.all([
        api.getHealth(),
        api.getCapabilities(),
        api.getProjects(),
      ]);

      setHealth(healthData);
      setCapabilities(capabilitiesData);
      setProjects(projectsData);
    } catch (err: unknown) {
      setIsError(true);
      if (err instanceof ApiClientError) {
        setErrorMessage(
          err.message.includes("Connection error")
            ? "Could not establish connection to local backend at 127.0.0.1:8000. Ensure the Python FastAPI server is running."
            : err.message,
        );
      } else if (err instanceof Error) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage("An unexpected error occurred while communicating with the local backend.");
      }
    } finally {
      setIsLoading(false);
      setIsRetrying(false);
    }
  }, []);

  useEffect(() => {
    // fetchAppData awaits the API; its setState runs in a promise callback,
    // not synchronously in this effect body.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchAppData();
  }, [fetchAppData]);

  const handleRetry = () => {
    setIsRetrying(true);
    fetchAppData();
  };

  /** Close the studio editor and return to the list it was opened from. */
  const handleClearSelection = useCallback(() => {
    setSelectedProjectId(null);
    setActiveTab(returnTab);
  }, [returnTab]);

  const handleCreateProject = async (name: string) => {
    const newProject = await api.createProject(name);
    setProjects((prev) => [newProject, ...prev]);
    setSelectedProjectId(newProject.id);
    setActiveTab("dashboard");
  };

  /**
   * Create an empty workspace without opening the studio editor.
   * Used by the dashboard when a gated YouTube import needs a destination.
   */
  const handleCreateWorkspace = async (name: string): Promise<Project> => {
    const newProject = await api.createProject(name);
    setProjects((prev) => [newProject, ...prev]);
    return newProject;
  };

  const handleDeleteProject = async (projectId: string) => {
    await api.deleteProject(projectId);
    setProjects((prev) => prev.filter((p) => p.id !== projectId));
    if (selectedProjectId === projectId) {
      setSelectedProjectId(null);
    }
  };

  const handleRenameProject = async (projectId: string, newName: string) => {
    const updated = await api.updateProject(projectId, newName);
    setProjects((prev) =>
      prev.map((p) =>
        p.id === projectId ? { ...p, name: updated.name, updated_at: updated.updated_at } : p,
      ),
    );
  };

  const handleDuplicateProject = async (projectId: string) => {
    const duplicate = await api.duplicateProject(projectId);
    setProjects((prev) => [duplicate, ...prev]);
  };

  const handleProjectMediaUpdated = (updatedProject: Project) => {
    setProjects((prev) => prev.map((p) => (p.id === updatedProject.id ? updatedProject : p)));
  };

  const handleDirectVideoDrop = async (file: File) => {
    const rawName = file.name.replace(/\.[^/.]+$/, "").trim() || "Untitled Project";
    const newProject = await api.createProject(rawName);
    setSelectedProjectId(newProject.id);
    setActiveTab("dashboard");
    try {
      const media = await api.uploadMedia(newProject.id, file);
      const updated = {
        ...newProject,
        media_count: 1,
        media_assets: [media],
      };
      setProjects((prev) => [updated, ...prev]);
    } catch (err) {
      console.error("Failed to upload video on direct drop:", err);
      setProjects((prev) => [newProject, ...prev]);
      throw err instanceof Error
        ? err
        : new Error("The video could not be imported into the new workspace.");
    }
  };

  // Live active workspace stats reported by ProjectDetailView for the status bar
  const [workspaceStats, setWorkspaceStats] = useState<{
    clipCount: number;
    hasTranscript: boolean;
  }>({
    clipCount: 0,
    hasTranscript: false,
  });

  const selectedProject = projects.find((p) => p.id === selectedProjectId) || null;
  const firstMedia = selectedProject?.media_assets?.[0];
  const hasMedia = Boolean(firstMedia);
  const mediaDetails = firstMedia
    ? `${firstMedia.width}×${firstMedia.height} ${firstMedia.video_codec.toUpperCase()}`
    : null;

  return (
    <ErrorBoundary title="The studio could not be rendered">
      <StudioLayout
        activeTab={activeTab}
        onTabChange={(tab) => {
          setActiveTab(tab);
          if (tab === "dashboard" || tab === "projects") {
            setSelectedProjectId(null);
          }
        }}
        onCreateProject={() => setIsCreateModalOpen(true)}
        projectCount={projects.length}
        selectedProjectName={selectedProject?.name}
        onClearSelectedProject={handleClearSelection}
        capabilities={capabilities}
        health={health}
        hasMedia={hasMedia}
        hasTranscript={selectedProject ? workspaceStats.hasTranscript : false}
        clipCount={selectedProject ? workspaceStats.clipCount : 0}
        mediaDetails={mediaDetails}
        searchQuery={globalSearchQuery}
        onSearchChange={setGlobalSearchQuery}
      >
        <div className="w-full space-y-6">
          {/* 1. Visible Local-Processing Privacy Copy (on dashboard and settings) */}
          {!selectedProject && <PrivacyBanner llm={capabilities?.llm ?? null} />}

          {/* 2. Loading State */}
          {isLoading && <LoadingSkeleton />}

          {/* 3. Error State */}
          {!isLoading && isError && (
            <ErrorMessage message={errorMessage} onRetry={handleRetry} isRetrying={isRetrying} />
          )}

          {/* 4. Capabilities (settings tab). The dashboard renders its own
            honest engine audit (features/dashboard/EngineStatusStrip). */}
          {!isLoading && capabilities && activeTab === "settings" && (
            <CapabilitiesCard capabilities={capabilities} />
          )}

          {/* 5. Main Workspace Area */}
          {!isLoading && !isError && (
            <>
              {activeTab === "settings" ? null : selectedProject ? (
                <ProjectDetailView
                  project={selectedProject}
                  onBack={handleClearSelection}
                  onDeleteProject={handleDeleteProject}
                  onRenameProject={handleRenameProject}
                  onMediaUpdated={handleProjectMediaUpdated}
                  capabilities={capabilities}
                  onStatsChange={setWorkspaceStats}
                />
              ) : activeTab === "dashboard" ? (
                <DashboardHome
                  projects={projects}
                  capabilities={capabilities}
                  health={health}
                  onSelectProject={(id) => {
                    setReturnTab("dashboard");
                    setSelectedProjectId(id);
                  }}
                  onOpenCreateModal={() => setIsCreateModalOpen(true)}
                  onOpenProjects={() => setActiveTab("projects")}
                  onDirectVideoDrop={handleDirectVideoDrop}
                  onCreateWorkspace={handleCreateWorkspace}
                  globalSearchQuery={globalSearchQuery}
                />
              ) : projects.length > 0 ? (
                <ProjectList
                  projects={projects}
                  onSelectProject={(id) => {
                    setReturnTab("projects");
                    setSelectedProjectId(id);
                    setActiveTab("dashboard");
                  }}
                  onOpenCreateModal={() => setIsCreateModalOpen(true)}
                  onDeleteProject={handleDeleteProject}
                  onRenameProject={handleRenameProject}
                  onDuplicateProject={handleDuplicateProject}
                  capabilities={capabilities}
                  health={health}
                  globalSearchQuery={globalSearchQuery}
                  onClearGlobalSearch={() => setGlobalSearchQuery("")}
                />
              ) : (
                <EmptyState onCreateProject={() => setIsCreateModalOpen(true)} />
              )}
            </>
          )}
        </div>

        {toast && (
          <Toast
            type={toast.type}
            message={toast.message}
            onClose={() => setToast(null)}
            autoDismissMs={6000}
          />
        )}

        {/* Create Project Modal */}
        <CreateProjectModal
          isOpen={isCreateModalOpen}
          onClose={() => setIsCreateModalOpen(false)}
          onCreate={handleCreateProject}
        />
      </StudioLayout>
    </ErrorBoundary>
  );
};

export default App;
