import React from "react";
import { Sliders, MessageSquare, Download } from "lucide-react";
import {
  InspectorTab,
  ClipEditSettings,
  CaptionStyleOptions,
  ExportSettings,
} from "../../../features/studio/types";
import { EditTabContent } from "./EditTabContent";
import { CaptionsTabContent } from "./CaptionsTabContent";
import { ExportTabContent } from "./ExportTabContent";

interface InspectorPanelProps {
  activeTab: InspectorTab;
  onTabChange: (tab: InspectorTab) => void;
  editSettings: ClipEditSettings;
  onUpdateEditSettings: (patch: Partial<ClipEditSettings>) => void;
  captionOptions: CaptionStyleOptions;
  onUpdateCaptionOptions: (patch: Partial<CaptionStyleOptions>) => void;
  exportSettings: ExportSettings;
  onUpdateExportSettings: (patch: Partial<ExportSettings>) => void;
  isExporting?: boolean;
  exportProgress?: number;
  onExport: () => Promise<void>;
  /** Full source duration in seconds (used by the Edit tab position bar). */
  sourceDurationSec?: number;
  downloadUrl?: string | null;
}

const TABS: { id: InspectorTab; label: string; icon: React.ElementType }[] = [
  { id: "edit", label: "Edit", icon: Sliders },
  { id: "captions", label: "Captions", icon: MessageSquare },
  { id: "export", label: "Export", icon: Download },
];

export const InspectorPanel: React.FC<InspectorPanelProps> = ({
  activeTab,
  onTabChange,
  editSettings,
  onUpdateEditSettings,
  captionOptions,
  onUpdateCaptionOptions,
  exportSettings,
  onUpdateExportSettings,
  isExporting,
  exportProgress,
  onExport,
  sourceDurationSec,
  downloadUrl,
}) => {
  return (
    <aside
      className="w-full h-full min-h-0 rounded-2xl border border-slate-800/80 bg-obsidian-900/60 backdrop-blur-md flex flex-col overflow-hidden select-none"
      data-testid="studio-inspector-panel"
    >
      {/* Top Inspector Navigation Tabs */}
      <div
        className="shrink-0 grid grid-cols-3 gap-1 p-2 border-b border-slate-800/80 bg-obsidian-950/60"
        role="tablist"
        aria-label="Clip inspector"
      >
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`inspector-tab-${tab.id}`}
              aria-controls={`inspector-panel-${tab.id}`}
              aria-selected={isActive}
              onClick={() => onTabChange(tab.id)}
              className={`flex items-center justify-center gap-1.5 py-2 rounded-xl text-xs font-semibold transition focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 cursor-pointer ${
                isActive
                  ? "bg-laqta-900/70 text-laqta-100 border border-laqta-600/50 shadow-sm"
                  : "text-slate-400 hover:text-white hover:bg-slate-800/60 border border-transparent"
              }`}
              data-testid={`inspector-tab-${tab.id}`}
            >
              <Icon className="h-3.5 w-3.5" aria-hidden="true" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* Tab Content Body */}
      <div
        className="flex-1 overflow-y-auto p-4"
        role="tabpanel"
        id={`inspector-panel-${activeTab}`}
        aria-labelledby={`inspector-tab-${activeTab}`}
      >
        {activeTab === "edit" && (
          <EditTabContent
            settings={editSettings}
            onUpdateSettings={onUpdateEditSettings}
            sourceDurationSec={sourceDurationSec}
          />
        )}

        {activeTab === "captions" && (
          <CaptionsTabContent options={captionOptions} onUpdateOptions={onUpdateCaptionOptions} />
        )}

        {activeTab === "export" && (
          <ExportTabContent
            settings={exportSettings}
            onUpdateSettings={onUpdateExportSettings}
            isExporting={isExporting}
            exportProgress={exportProgress}
            onExport={onExport}
            downloadUrl={downloadUrl}
          />
        )}
      </div>
    </aside>
  );
};
