import React from "react";
import { Download, FileVideo, HardDrive, Cpu, Layers, Sparkles, CheckCircle2 } from "lucide-react";
import { ExportSettings } from "../../../features/studio/types";
import { Switch } from "../../ui/Switch";

interface ExportTabContentProps {
  settings: ExportSettings;
  onUpdateSettings: (patch: Partial<ExportSettings>) => void;
  isExporting?: boolean;
  exportProgress?: number;
  onExport: () => Promise<void>;
  downloadUrl?: string | null;
}

export const ExportTabContent: React.FC<ExportTabContentProps> = ({
  settings,
  onUpdateSettings,
  isExporting = false,
  exportProgress = 0,
  onExport,
  downloadUrl = null,
}) => {
  return (
    <div className="space-y-5 text-xs select-none" data-testid="export-tab-content">
      {/* Section Title */}
      <h3 className="text-sm font-bold text-white tracking-tight">Export Settings</h3>

      {/* 1. File Name Input */}
      <div className="space-y-1.5">
        <label className="text-slate-300 font-semibold block flex items-center space-x-1.5">
          <FileVideo className="h-3.5 w-3.5 text-laqta-200" />
          <span>Output File Name</span>
        </label>
        <input
          type="text"
          value={settings.fileName}
          onChange={(e) => onUpdateSettings({ fileName: e.target.value })}
          placeholder="Laqta_Short.mp4"
          className="w-full px-3 py-2 rounded-xl bg-obsidian-950 border border-slate-800 text-white placeholder-slate-500 focus:outline-none focus:border-cyan-400 font-mono text-xs"
          data-testid="export-filename-input"
        />
      </div>

      {/* 2. Resolution Selector */}
      <div className="space-y-2">
        <label className="text-slate-300 font-semibold block">Resolution</label>
        <div className="space-y-1.5">
          {(
            [
              {
                id: "1080p",
                label: "1080p Full HD (1080×1920)",
                recommended: true,
              },
              {
                id: "4k",
                label: "4K Ultra HD (2160×3840)",
                recommended: false,
              },
              {
                id: "720p",
                label: "720p Mobile (720×1280)",
                recommended: false,
              },
            ] as const
          ).map((res) => {
            const isSelected = settings.resolution === res.id;
            return (
              <button
                key={res.id}
                type="button"
                onClick={() => onUpdateSettings({ resolution: res.id })}
                className={`w-full flex items-center justify-between p-2.5 rounded-xl border transition ${
                  isSelected
                    ? "bg-laqta-900/70 border-laqta-500/60 text-white shadow-sm"
                    : "bg-obsidian-950 border-slate-800 text-slate-400 hover:text-white hover:border-slate-700"
                }`}
                data-testid={`res-option-${res.id}`}
              >
                <span className="font-semibold">{res.label}</span>
                {res.recommended && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-laqta-950 text-laqta-200 border border-laqta-800/50">
                    Recommended
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* 3. Video Format Selector */}
      <div className="space-y-2">
        <label className="text-slate-300 font-semibold block">Format</label>
        <div className="grid grid-cols-2 gap-2">
          {(
            [
              { id: "mp4", label: "MP4 (H.264 + AAC)" },
              { id: "mov", label: "MOV (Apple ProRes)" },
            ] as const
          ).map((fmt) => {
            const isSelected = settings.format === fmt.id;
            return (
              <button
                key={fmt.id}
                type="button"
                onClick={() => onUpdateSettings({ format: fmt.id })}
                className={`p-2.5 rounded-xl border text-center font-medium transition ${
                  isSelected
                    ? "bg-laqta-900/70 border-laqta-500/60 text-white shadow-sm"
                    : "bg-obsidian-950 border-slate-800 text-slate-400 hover:text-white hover:border-slate-700"
                }`}
                data-testid={`fmt-option-${fmt.id}`}
              >
                <span className="font-semibold block text-[11px]">{fmt.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* 4. Burn-in Subtitles Toggle */}
      <div className="p-3 rounded-xl bg-obsidian-950/70 border border-slate-800/80 flex items-center justify-between">
        <div className="space-y-0.5 pr-2 min-w-0">
          <div className="flex items-center gap-1.5 text-white font-semibold">
            <Layers className="h-3.5 w-3.5 text-laqta-200" aria-hidden="true" />
            <span>Burn-in Subtitles</span>
          </div>
          <p className="text-[10px] text-slate-400 leading-snug">
            Hardcode subtitles directly onto video frames
          </p>
        </div>
        <Switch
          checked={settings.burnInSubtitles}
          onChange={(burnInSubtitles) => onUpdateSettings({ burnInSubtitles })}
          label="Burn-in Subtitles"
          testId="burn-in-subtitles-toggle"
        />
      </div>

      {/* 5. Rough Estimates (informational, not guarantees) */}
      <div className="p-3 rounded-xl bg-obsidian-950/70 border border-slate-800/80 space-y-1.5 text-[11px] text-slate-400">
        <div className="flex justify-between items-center">
          <span className="flex items-center space-x-1.5">
            <HardDrive className="h-3 w-3 text-slate-500" />
            <span>File Size</span>
          </span>
          <span className="font-mono text-slate-200 font-semibold">depends on clip length</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="flex items-center space-x-1.5">
            <Cpu className="h-3 w-3 text-slate-500" />
            <span>Render Time (CPU)</span>
          </span>
          <span className="font-mono text-slate-200 font-semibold">varies by hardware</span>
        </div>
      </div>

      {/* 6. Live Rendering Progress Bar */}
      {isExporting && (
        <div
          className="space-y-2 p-3.5 rounded-xl bg-laqta-950/40 border border-laqta-800/60 shadow-lg"
          data-testid="export-progress-container"
        >
          <div className="flex justify-between items-center text-[11px]">
            <span className="text-laqta-100 font-semibold flex items-center gap-1.5">
              <Sparkles className="h-3.5 w-3.5 text-neon-cyan animate-spin" aria-hidden="true" />
              <span>Rendering 9:16 Short in background...</span>
            </span>
            <span className="font-mono text-cyan-300 font-bold">{exportProgress}%</span>
          </div>
          <div className="w-full h-2 bg-obsidian-950 rounded-full overflow-hidden border border-slate-800">
            <div
              className="h-full laqta-gradient-surface transition-all duration-300 rounded-full"
              style={{ width: `${Math.max(5, exportProgress)}%` }}
            />
          </div>
        </div>
      )}

      {/* 7. Ready Download Card */}
      {downloadUrl && !isExporting && (
        <div
          className="p-3.5 rounded-xl bg-emerald-950/60 border border-emerald-500/50 shadow-lg space-y-2.5"
          data-testid="export-success-card"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-emerald-300 font-bold text-xs">
              <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" aria-hidden="true" />
              <span>Render Complete</span>
            </div>
            <span className="text-[10px] text-emerald-300 font-mono bg-emerald-900/60 px-2 py-0.5 rounded-full border border-emerald-700/50">
              MP4 Ready
            </span>
          </div>
          <p className="text-[11px] text-emerald-200/90 leading-snug">
            Your short is ready with burned-in subtitles and 9:16 framing.
          </p>
          <a
            href={downloadUrl}
            download={settings.fileName || "Laqta_Short.mp4"}
            target="_blank"
            rel="noopener noreferrer"
            className="w-full py-2.5 px-3 rounded-xl font-bold text-xs text-white bg-linear-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 border border-emerald-400/50 shadow-md flex items-center justify-center gap-2 transition-all active:scale-[0.98] cursor-pointer"
            data-testid="download-rendered-short-btn"
          >
            <Download className="h-4 w-4" aria-hidden="true" />
            <span>Download Short (MP4)</span>
          </a>
        </div>
      )}

      {/* 8. Export Processing Notice */}
      <div className="flex items-start space-x-2 text-[11px] text-cyan-300 bg-cyan-950/40 border border-cyan-800/50 rounded-xl px-3 py-2">
        <Sparkles className="h-3.5 w-3.5 shrink-0 mt-0.5" aria-hidden="true" />
        <span>
          Local-first rendering: Export processes via FFmpeg in the background with burned-in
          subtitles and 9:16 vertical crop.
        </span>
      </div>

      {/* 9. Primary Export CTA Button */}
      <button
        type="button"
        onClick={onExport}
        disabled={isExporting}
        className="w-full py-3 px-4 rounded-xl font-bold text-sm text-white laqta-gradient-surface hover:brightness-110 shadow-laqta-glow flex items-center justify-center gap-2 transition-[filter,transform] active:scale-[0.98] disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 focus-visible:ring-offset-2 focus-visible:ring-offset-obsidian-950"
        data-testid="export-short-btn"
      >
        {isExporting ? (
          <>
            <Sparkles className="h-4 w-4 animate-spin text-white" aria-hidden="true" />
            <span>Exporting Short ({exportProgress}%)...</span>
          </>
        ) : (
          <>
            <Download className="h-4 w-4" aria-hidden="true" />
            <span>{downloadUrl ? "Re-Export Short" : "Export Short"}</span>
          </>
        )}
      </button>

      <p className="text-[10px] leading-relaxed text-slate-500">
        Rendering runs locally in the background. With{" "}
        <span className="text-slate-300">Karaoke Word Sync</span> on, the selected clip is
        additionally re-transcribed on this machine to time every word to the speech — that adds a
        couple of minutes.
      </p>
    </div>
  );
};
