import React, { useEffect, useRef } from "react";
import {
  LayoutDashboard,
  PlusCircle,
  FolderKanban,
  Sliders,
  Github,
  ShieldCheck,
  Star,
  X,
} from "lucide-react";
import { BrandLogo } from "../ui/BrandLogo";
import { REPO_URL } from "../../lib/brand";
import { CapabilitiesResponse } from "../../types/capabilities";

export type StudioNavTab = "dashboard" | "projects" | "settings";

interface StudioSidebarProps {
  activeTab: StudioNavTab;
  onTabChange: (tab: StudioNavTab) => void;
  onCreateProject: () => void;
  projectCount: number;
  capabilities: CapabilitiesResponse | null;
  isOpenMobile?: boolean;
  onCloseMobile?: () => void;
}

export const StudioSidebar: React.FC<StudioSidebarProps> = ({
  activeTab,
  onTabChange,
  onCreateProject,
  projectCount,
  capabilities,
  isOpenMobile = false,
  onCloseMobile,
}) => {
  // Escape closes the mobile drawer; backdrop is mouse-only by design.
  useEffect(() => {
    if (!isOpenMobile || !onCloseMobile) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCloseMobile();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpenMobile, onCloseMobile]);

  // Keep the nav item for the active tab in view when the drawer scrolls.
  const activeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const el = activeRef.current;
    // `scrollIntoView` is absent in non-browser test environments.
    if (el && typeof el.scrollIntoView === "function") {
      el.scrollIntoView({ block: "nearest" });
    }
  }, [activeTab]);

  const navItemClass = (isActive: boolean) =>
    `group relative w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 ${
      isActive
        ? "bg-purple-950/60 text-white border border-purple-500/40 shadow-[0_0_14px_rgba(168,85,247,0.18)]"
        : "text-slate-400 hover:text-white hover:bg-slate-800/50 border border-transparent"
    }`;

  const navIconClass = (isActive: boolean) =>
    `h-4 w-4 shrink-0 transition-colors ${
      isActive ? "text-neon-cyan" : "text-slate-500 group-hover:text-slate-300"
    }`;

  return (
    <>
      {/* Mobile Backdrop */}
      {isOpenMobile && (
        <div
          className="fixed inset-0 bg-obsidian-950/80 backdrop-blur-sm z-40 lg:hidden"
          onClick={onCloseMobile}
          data-testid="sidebar-mobile-backdrop"
          aria-hidden="true"
        />
      )}

      <aside
        className={`fixed lg:static top-0 bottom-0 left-0 z-50 w-[264px] bg-obsidian-900/90 border-r border-slate-800/80 backdrop-blur-md flex flex-col justify-between transition-transform duration-300 ease-in-out ${
          isOpenMobile ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
        }`}
        data-testid="studio-sidebar"
        aria-label="Studio navigation"
      >
        {/* Top: Brand Header & Mobile Close */}
        <div className="p-4 border-b border-slate-800/80 flex items-center justify-between">
          <BrandLogo size="md" showSubtitle={true} />
          {onCloseMobile && (
            <button
              onClick={onCloseMobile}
              className="lg:hidden p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
              aria-label="Close menu"
            >
              <X className="h-5 w-5" />
            </button>
          )}
        </div>

        {/* Center: Primary action + Navigation */}
        <div className="flex-1 px-3 py-4 space-y-5 overflow-y-auto">
          {/* Primary action — creating a workspace is the main thing a user
              comes here to do, so it gets a filled CTA instead of sitting
              between two navigation entries. */}
          <button
            onClick={onCreateProject}
            data-testid="sidebar-create-project-btn"
            className="group relative w-full flex items-center justify-center gap-2 overflow-hidden rounded-xl laqta-gradient-surface px-4 py-2.5 text-sm font-semibold text-white shadow-laqta-glow transition-[filter,transform] duration-200 hover:brightness-110 active:scale-[0.98] focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-300 cursor-pointer"
          >
            <span
              aria-hidden="true"
              className="pointer-events-none absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/20 to-transparent group-hover:translate-x-full transition-transform duration-700"
            />
            <PlusCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span>Create New Project</span>
          </button>

          {/* Primary Navigation Menu */}
          <nav className="space-y-1" aria-label="Main navigation">
            <p className="px-3 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">
              Workspace
            </p>

            <button
              ref={activeTab === "dashboard" ? activeRef : undefined}
              onClick={() => onTabChange("dashboard")}
              aria-current={activeTab === "dashboard" ? "page" : undefined}
              className={navItemClass(activeTab === "dashboard")}
            >
              <LayoutDashboard
                className={navIconClass(activeTab === "dashboard")}
                aria-hidden="true"
              />
              <span className="flex-1 text-left">Dashboard</span>
              {activeTab === "dashboard" && (
                <span
                  className="h-1.5 w-1.5 rounded-full bg-neon-cyan shadow-neon-cyan"
                  aria-hidden="true"
                />
              )}
            </button>

            <button
              onClick={() => onTabChange("projects")}
              aria-current={activeTab === "projects" ? "page" : undefined}
              className={navItemClass(activeTab === "projects")}
            >
              <FolderKanban className={navIconClass(activeTab === "projects")} aria-hidden="true" />
              <span className="flex-1 text-left">My Projects</span>
              <span className="text-[11px] font-mono px-1.5 py-0.5 rounded-md bg-slate-800/80 text-slate-400 border border-slate-700/60">
                {projectCount}
              </span>
            </button>
          </nav>

          {/* System Navigation */}
          <nav className="space-y-1" aria-label="System navigation">
            <p className="px-3 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">
              System
            </p>

            <button
              onClick={() => onTabChange("settings")}
              aria-current={activeTab === "settings" ? "page" : undefined}
              className={navItemClass(activeTab === "settings")}
            >
              <Sliders className={navIconClass(activeTab === "settings")} aria-hidden="true" />
              <span className="flex-1 text-left">Settings &amp; Engine</span>
              {capabilities?.ffmpeg.available ? (
                <span
                  className="h-2 w-2 rounded-full bg-neon-emerald animate-pulse-glow"
                  role="status"
                  aria-label="FFmpeg engine available"
                  title="FFmpeg engine available"
                />
              ) : (
                <span
                  className="h-2 w-2 rounded-full bg-amber-400"
                  role="status"
                  aria-label="FFmpeg engine missing"
                  title="FFmpeg engine missing"
                />
              )}
            </button>
          </nav>
        </div>

        {/* Bottom Cards: Open Source Card & Local Workspace Profile */}
        <div className="p-3 border-t border-slate-800/80 space-y-2.5">
          {/* Open Source GitHub Card */}
          <div className="p-3 rounded-xl bg-obsidian-950/70 border border-slate-800/80 space-y-2.5">
            <div className="flex items-center space-x-2.5">
              <Github className="h-4 w-4 text-slate-300 shrink-0" />
              <div className="min-w-0">
                <p className="text-xs font-semibold text-white">Open Source</p>
                <p className="text-[10px] text-slate-400 truncate">
                  Built by the community, for creators.
                </p>
              </div>
              <span className="ml-auto text-[10px] px-2 py-0.5 rounded-full bg-purple-900/40 text-laqta-200 border border-purple-700/40 shrink-0">
                v{capabilities?.version ?? "0.1.0"}
              </span>
            </div>
            <a
              href={REPO_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="w-full inline-flex items-center justify-center space-x-1.5 py-1.5 rounded-lg bg-slate-800/80 hover:bg-slate-700/80 border border-slate-700/60 text-slate-200 text-[11px] font-semibold transition cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
            >
              <Star className="h-3.5 w-3.5 text-amber-400" />
              <span>Star on GitHub</span>
            </a>
          </div>

          {/* Local Workspace Profile Row (no accounts — fully local) */}
          <div
            className="p-2.5 rounded-xl bg-obsidian-950/50 border border-slate-800/50 flex items-center justify-between"
            title="Laqta runs entirely on this device — no accounts, no cloud, no telemetry."
          >
            <div className="flex items-center space-x-2.5 min-w-0">
              <div className="h-8 w-8 rounded-full bg-gradient-to-tr from-laqta-600 to-cyan-400 p-0.5 shrink-0">
                <div className="h-full w-full rounded-full bg-obsidian-950 flex items-center justify-center">
                  <ShieldCheck className="h-3.5 w-3.5 text-neon-cyan" />
                </div>
              </div>
              <div className="min-w-0">
                <p className="text-xs font-semibold text-white truncate">Local Workspace</p>
                <p className="text-[10px] text-slate-400 truncate">
                  {(capabilities?.hardware.device ?? "cpu").toUpperCase()} · 100% private
                </p>
              </div>
            </div>
            <ShieldCheck className="h-3.5 w-3.5 text-slate-600 shrink-0" />
          </div>
        </div>
      </aside>
    </>
  );
};
