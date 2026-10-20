import React, { useState } from "react";
import { StudioSidebar, StudioNavTab } from "./StudioSidebar";
import { StudioTopHeader } from "./StudioTopHeader";
import { StudioStatusBar } from "./StudioStatusBar";
import { CapabilitiesResponse } from "../../types/capabilities";
import { HealthResponse } from "../../types/health";

interface StudioLayoutProps {
  children: React.ReactNode;
  activeTab: StudioNavTab;
  onTabChange: (tab: StudioNavTab) => void;
  onCreateProject: () => void;
  projectCount: number;
  selectedProjectName?: string | null;
  onClearSelectedProject?: () => void;
  capabilities: CapabilitiesResponse | null;
  health: HealthResponse | null;
  hasMedia?: boolean;
  hasTranscript?: boolean;
  clipCount?: number;
  mediaDetails?: string | null;
  /** Optional controlled search state lifted to App so the header query filters views. */
  searchQuery?: string;
  onSearchChange?: (query: string) => void;
}

export const StudioLayout: React.FC<StudioLayoutProps> = ({
  children,
  activeTab,
  onTabChange,
  onCreateProject,
  projectCount,
  selectedProjectName,
  onClearSelectedProject,
  capabilities,
  health,
  hasMedia = false,
  hasTranscript = false,
  clipCount = 0,
  mediaDetails = null,
  searchQuery,
  onSearchChange,
}) => {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [internalSearchQuery, setInternalSearchQuery] = useState("");
  const isSearchControlled = searchQuery !== undefined;
  const activeSearchQuery = isSearchControlled ? searchQuery : internalSearchQuery;
  const handleSearchChange = onSearchChange ?? setInternalSearchQuery;

  return (
    <div
      className="h-screen w-screen overflow-hidden bg-obsidian-950 text-slate-100 flex flex-col font-sans"
      data-testid="studio-layout"
    >
      <div className="flex-1 flex overflow-hidden">
        {/* Skip link for keyboard users */}
        <a
          href="#studio-main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-[70] focus:px-3 focus:py-1.5 focus:rounded-lg focus:bg-laqta-600 focus:text-white focus:text-xs focus:font-semibold"
        >
          Skip to main content
        </a>

        {/* Left Sidebar */}
        <StudioSidebar
          activeTab={activeTab}
          onTabChange={(tab) => {
            onTabChange(tab);
            setIsMobileMenuOpen(false);
          }}
          onCreateProject={() => {
            onCreateProject();
            setIsMobileMenuOpen(false);
          }}
          projectCount={projectCount}
          capabilities={capabilities}
          isOpenMobile={isMobileMenuOpen}
          onCloseMobile={() => setIsMobileMenuOpen(false)}
        />

        {/* Center Workbench */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {/* Top Header */}
          <StudioTopHeader
            onOpenMobileMenu={() => setIsMobileMenuOpen(true)}
            searchQuery={activeSearchQuery}
            onSearchChange={handleSearchChange}
            capabilities={capabilities}
            health={health}
            selectedProjectName={selectedProjectName}
            onClearSelectedProject={onClearSelectedProject}
          />

          {/* Main Production Workspace Body */}
          <main
            id="studio-main-content"
            tabIndex={-1}
            className="flex-1 overflow-y-auto bg-obsidian-950 p-4 sm:p-6 lg:p-8 focus:outline-none studio-ambient"
          >
            <div className="mx-auto w-full max-w-[1900px] space-y-6">{children}</div>
          </main>
        </div>
      </div>

      {/* Persistent Global Status Bar */}
      <StudioStatusBar
        hasMedia={hasMedia}
        hasTranscript={hasTranscript}
        clipCount={clipCount}
        mediaDetails={mediaDetails}
        storageWritable={capabilities?.storage.writable ?? true}
      />
    </div>
  );
};
