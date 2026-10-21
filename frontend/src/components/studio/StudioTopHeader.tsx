import React, { useEffect, useState } from "react";
import { Search, Menu, Maximize2, Minimize2, Command, ChevronRight, X } from "lucide-react";
import { CapabilitiesResponse } from "../../types/capabilities";
import { HealthResponse } from "../../types/health";

interface StudioTopHeaderProps {
  onOpenMobileMenu?: () => void;
  searchQuery: string;
  onSearchChange: (query: string) => void;
  capabilities: CapabilitiesResponse | null;
  health: HealthResponse | null;
  selectedProjectName?: string | null;
  onClearSelectedProject?: () => void;
}

export const StudioTopHeader: React.FC<StudioTopHeaderProps> = ({
  onOpenMobileMenu,
  searchQuery,
  onSearchChange,
  capabilities,
  health,
  selectedProjectName,
  onClearSelectedProject,
}) => {
  const [isFullscreen, setIsFullscreen] = useState(Boolean(document.fullscreenElement));

  // Keep the toggle state in sync when the user leaves fullscreen with Esc/F11.
  useEffect(() => {
    const handleChange = () => {
      setIsFullscreen(Boolean(document.fullscreenElement));
    };
    document.addEventListener("fullscreenchange", handleChange);
    return () => document.removeEventListener("fullscreenchange", handleChange);
  }, []);

  const focusSearch = () => {
    document.querySelector<HTMLInputElement>('[data-testid="studio-search-input"]')?.focus();
  };

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {});
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen().catch(() => {});
      }
    }
  };

  return (
    <header
      className="h-14 shrink-0 border-b border-slate-800/80 bg-obsidian-900/80 backdrop-blur-md px-3 sm:px-4 flex items-center justify-between gap-3 z-20"
      data-testid="studio-top-header"
    >
      {/* Left: Mobile Menu Trigger & Project Breadcrumb */}
      <div className="flex items-center gap-2 min-w-0">
        <button
          onClick={onOpenMobileMenu}
          className="lg:hidden p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
          aria-label="Open sidebar"
        >
          <Menu className="h-5 w-5" />
        </button>

        {selectedProjectName ? (
          <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-xs min-w-0">
            <button
              onClick={onClearSelectedProject}
              className="shrink-0 rounded-md px-1.5 py-1 text-slate-400 hover:text-white hover:bg-slate-800/70 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 cursor-pointer"
            >
              Projects
            </button>
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-slate-700" aria-hidden="true" />
            <span
              className="font-semibold text-white truncate max-w-[120px] sm:max-w-[220px]"
              data-testid="header-project-name"
              title={selectedProjectName}
            >
              Project: {selectedProjectName}
            </span>
          </nav>
        ) : (
          <div className="hidden sm:flex items-center gap-2 min-w-0">
            <span className="text-xs font-semibold text-slate-300 whitespace-nowrap">
              Studio Workspace
            </span>
            <span
              className="h-1.5 w-1.5 rounded-full bg-neon-cyan animate-pulse-glow"
              aria-hidden="true"
            />
          </div>
        )}
      </div>

      {/* Center: Search Bar */}
      <div className="flex-1 max-w-xl mx-auto">
        <div className="relative">
          <Search
            className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none"
            aria-hidden="true"
          />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search projects, clips, transcripts..."
            aria-label="Search projects, clips, transcripts"
            className="w-full h-9 pl-9 pr-20 rounded-xl bg-obsidian-950/80 border border-slate-800/80 text-sm text-slate-200 placeholder-slate-500 transition focus:outline-none focus:border-laqta-500/60 focus:ring-1 focus:ring-purple-500/40 hover:border-slate-700"
            data-testid="studio-search-input"
          />

          {searchQuery ? (
            <button
              type="button"
              onClick={() => onSearchChange("")}
              aria-label="Clear search"
              title="Clear search"
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded-md text-slate-500 hover:text-white hover:bg-slate-800 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 cursor-pointer"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          ) : (
            <button
              type="button"
              onClick={focusSearch}
              className="absolute right-2 top-1/2 -translate-y-1/2 hidden sm:flex items-center gap-0.5 min-h-[24px] text-[10px] text-slate-500 bg-slate-900 px-1.5 py-1 rounded border border-slate-800 hover:text-slate-300 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 cursor-pointer"
              aria-label="Focus search (Ctrl+K)"
              title="Ctrl+K"
            >
              <Command className="h-2.5 w-2.5" aria-hidden="true" />
              <span>K</span>
            </button>
          )}
        </div>
      </div>

      {/* Right: Hardware Telemetry Pill & Action Icons */}
      <div className="flex items-center gap-2 shrink-0">
        {/* Hardware Status Pill — the dot reflects the *reported* state.
            A stopped job worker means queued jobs would never run, so the
            studio must not show a healthy green dot in that case. */}
        <div
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-full bg-obsidian-950/80 border border-slate-800 text-xs text-slate-300 shadow-sm"
          title={`Status: ${health?.status || "unknown"} • Worker: ${health?.worker || "unknown"} • Storage: ${capabilities?.storage.data_dir || "local"}`}
          data-testid="studio-health-pill"
        >
          <span
            className={`h-2 w-2 rounded-full ${
              health?.status === "degraded"
                ? "bg-amber-400"
                : "bg-neon-emerald animate-pulse-glow"
            }`}
            aria-hidden="true"
          />
          <span className="font-medium text-[11px] text-slate-200 hidden sm:inline">
            {capabilities ? `${capabilities.hardware.device.toUpperCase()} Mode` : "CPU Mode"}
          </span>
          <span className="text-slate-500 hidden sm:inline" aria-hidden="true">
            •
          </span>
          <span
            className={`text-[11px] ${
              health?.status === "degraded" ? "text-amber-300" : "text-neon-cyan"
            }`}
          >
            {health?.status === "degraded" ? "Worker stopped" : "Local 127.0.0.1"}
          </span>
        </div>

        {/* Fullscreen Button */}
        <button
          onClick={toggleFullscreen}
          className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800/60 transition hidden sm:flex items-center focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 cursor-pointer"
          aria-label={isFullscreen ? "Exit Fullscreen" : "Enter Fullscreen"}
          title={isFullscreen ? "Exit Fullscreen" : "Enter Fullscreen"}
        >
          {isFullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
        </button>
      </div>
    </header>
  );
};
