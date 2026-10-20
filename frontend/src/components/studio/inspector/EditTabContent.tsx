import React from "react";
import {
  Smartphone,
  Monitor,
  Square,
  UserCheck,
  Camera,
  SplitSquareVertical,
  Clock,
  Scissors,
} from "lucide-react";
import { ClipEditSettings, AspectRatioMode } from "../../../features/studio/types";
import { formatMsAsClock } from "../../../lib/i18n/bidi";
import { Switch } from "../../ui/Switch";

interface EditTabContentProps {
  settings: ClipEditSettings;
  onUpdateSettings: (patch: Partial<ClipEditSettings>) => void;
  /** Full source duration — used to draw the clip position inside the media. */
  sourceDurationSec?: number;
}

const ASPECT_TILES: { id: AspectRatioMode; label: string; icon: React.ElementType }[] = [
  { id: "9:16", label: "Portrait", icon: Smartphone },
  { id: "16:9", label: "Widescreen", icon: Monitor },
  { id: "1:1", label: "Square", icon: Square },
];

export const EditTabContent: React.FC<EditTabContentProps> = ({
  settings,
  onUpdateSettings,
  sourceDurationSec,
}) => {
  const clipDurationSec = Math.max(0, settings.endSec - settings.startSec);
  const sourceDuration = Math.max(clipDurationSec, sourceDurationSec ?? 0);
  const clipStartPct =
    sourceDuration > 0 ? Math.max(0, Math.min(100, (settings.startSec / sourceDuration) * 100)) : 0;
  const clipWidthPct =
    sourceDuration > 0
      ? Math.max(2, Math.min(100 - clipStartPct, (clipDurationSec / sourceDuration) * 100))
      : 100;

  return (
    <div className="space-y-5 text-xs select-none" data-testid="edit-tab-content">
      {/* Section Title */}
      <div>
        <h3 className="text-sm font-bold text-white tracking-tight">Clip Settings</h3>
        <p className="text-[11px] text-slate-500 mt-0.5">
          Trim, frame and stabilise the selected short.
        </p>
      </div>

      {/* 1. Clip Title Input */}
      <div className="space-y-1.5">
        <label htmlFor="inspector-clip-name" className="text-slate-300 font-semibold block">
          Clip Title
        </label>
        <input
          id="inspector-clip-name"
          type="text"
          value={settings.clipName}
          onChange={(e) => onUpdateSettings({ clipName: e.target.value })}
          placeholder="Clip Title"
          className="w-full px-3 py-2.5 rounded-xl bg-obsidian-950 border border-slate-800 text-white placeholder-slate-500 transition focus:outline-none focus:border-laqta-400 focus:ring-1 focus:ring-laqta-400/30 font-medium"
          data-testid="clip-name-input"
        />
      </div>

      {/* 2. Timing Range Display */}
      <div className="p-3 rounded-xl bg-obsidian-950/70 border border-slate-800/80 space-y-3">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-slate-300 font-semibold">
            <Clock className="h-3.5 w-3.5 text-laqta-200" aria-hidden="true" />
            <span>Time Range</span>
          </span>
          <span className="inline-flex items-center gap-1 font-mono text-white font-semibold px-2 py-0.5 rounded-md bg-laqta-950/70 border border-laqta-700/60 text-[11px]">
            <Scissors className="h-3 w-3 text-laqta-200" aria-hidden="true" />
            {clipDurationSec.toFixed(1)}s
          </span>
        </div>

        {/* Position of the clip inside the source media */}
        <div
          className="relative h-1.5 rounded-full bg-slate-800/80 overflow-hidden"
          title="Clip position inside the source video"
        >
          <div
            className="absolute inset-y-0 rounded-full laqta-gradient-surface"
            style={{ left: `${clipStartPct}%`, width: `${clipWidthPct}%` }}
          />
        </div>

        <div className="grid grid-cols-2 gap-2 text-[11px] font-mono">
          <div className="p-2.5 rounded-lg bg-slate-900/60 border border-slate-800">
            <span className="text-slate-500 block text-[9px] tracking-[0.12em]">START</span>
            <span className="text-slate-200">
              {formatMsAsClock(Math.round(settings.startSec * 1000))}
            </span>
          </div>
          <div className="p-2.5 rounded-lg bg-slate-900/60 border border-slate-800">
            <span className="text-slate-500 block text-[9px] tracking-[0.12em]">END</span>
            <span className="text-slate-200">
              {formatMsAsClock(Math.round(settings.endSec * 1000))}
            </span>
          </div>
        </div>
      </div>

      {/* 3. Aspect Ratio Selector Tiles */}
      <div className="space-y-2">
        <label className="text-slate-300 font-semibold block">Aspect Ratio</label>
        <div className="grid grid-cols-3 gap-2">
          {ASPECT_TILES.map((item) => {
            const Icon = item.icon;
            const isSelected = settings.aspectRatio === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onUpdateSettings({ aspectRatio: item.id as AspectRatioMode })}
                aria-pressed={isSelected}
                className={`flex flex-col items-center justify-center gap-0.5 p-2.5 rounded-xl border transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 cursor-pointer ${
                  isSelected
                    ? "bg-laqta-900/70 border-laqta-500/60 text-white shadow-neon-purple/40"
                    : "bg-obsidian-950 border-slate-800 text-slate-400 hover:text-white hover:border-slate-700"
                }`}
                data-testid={`ar-tile-${item.id}`}
              >
                <Icon
                  className={`h-4 w-4 mb-0.5 ${isSelected ? "text-laqta-200" : "text-slate-400"}`}
                  aria-hidden="true"
                />
                <span className="font-bold text-[11px]">{item.id}</span>
                <span className="text-[9px] text-slate-400">{item.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* 4. Auto Reframe Toggle */}
      <div className="p-3 rounded-xl bg-obsidian-950/70 border border-slate-800/80 flex items-center justify-between gap-3">
        <div className="space-y-0.5 pr-2 min-w-0">
          <div className="flex items-center gap-1.5 text-white font-semibold">
            <UserCheck className="h-3.5 w-3.5 text-neon-cyan" aria-hidden="true" />
            <span>Auto Reframe</span>
          </div>
          <p className="text-[10px] text-slate-400 leading-snug">
            Center crop tracks active speaker face
          </p>
        </div>
        <Switch
          checked={settings.autoReframe}
          onChange={(autoReframe) => onUpdateSettings({ autoReframe })}
          label="Auto Reframe"
          testId="auto-reframe-toggle"
        />
      </div>

      {/* 5. Camera Smoothing Slider */}
      <div className="space-y-2.5 p-3 rounded-xl bg-obsidian-950/70 border border-slate-800/80">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-slate-300 font-semibold">
            <Camera className="h-3.5 w-3.5 text-laqta-200" aria-hidden="true" />
            <span>Camera Smoothing</span>
          </span>
          <span className="font-mono text-laqta-200 font-bold">{settings.motionSmoothing}%</span>
        </div>
        <input
          type="range"
          min={0}
          max={100}
          step={5}
          value={settings.motionSmoothing}
          onChange={(e) => onUpdateSettings({ motionSmoothing: parseInt(e.target.value, 10) })}
          aria-label="Camera Smoothing"
          className="w-full h-4 cursor-pointer focus:outline-none"
          data-testid="motion-smoothing-slider"
        />
        <div className="flex justify-between text-[9px] text-slate-400">
          <span>Dynamic</span>
          <span>Ultra Smooth</span>
        </div>
      </div>

      {/* 6. Split-Screen Mode Toggle */}
      <div className="p-3 rounded-xl bg-obsidian-950/70 border border-slate-800/80 flex items-center justify-between gap-3">
        <div className="space-y-0.5 pr-2 min-w-0">
          <div className="flex items-center gap-1.5 text-white font-semibold">
            <SplitSquareVertical className="h-3.5 w-3.5 text-amber-400" aria-hidden="true" />
            <span>Split Screen</span>
          </div>
          <p className="text-[10px] text-slate-400 leading-snug">
            Two-speaker vertical split layout
          </p>
        </div>
        <Switch
          checked={settings.splitScreen}
          onChange={(splitScreen) => onUpdateSettings({ splitScreen })}
          label="Split Screen"
          testId="split-screen-toggle"
        />
      </div>
    </div>
  );
};
