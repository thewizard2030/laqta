import React from "react";
import { Sparkles, Type, AlignVerticalJustifyCenter, Palette, Wand2 } from "lucide-react";
import { CaptionStyleOptions, CaptionPreset } from "../../../features/studio/types";
import { Switch } from "../../ui/Switch";

interface CaptionsTabContentProps {
  options: CaptionStyleOptions;
  onUpdateOptions: (patch: Partial<CaptionStyleOptions>) => void;
}

const COLOR_SWATCHES = [
  { label: "Neon Cyan", color: "#00F2FE" },
  { label: "Neon Purple", color: "#A855F7" },
  { label: "Electric Yellow", color: "#FACC15" },
  { label: "Emerald", color: "#10B981" },
  { label: "Pure White", color: "#FFFFFF" },
];

/**
 * Font families that are actually installed on a typical Linux desktop and
 * cover Arabic. A missing family silently falls back to a system default
 * through fontconfig, so the list names real families rather than popular
 * ones that may not be present.
 */
const FONT_FAMILIES = [
  { id: "Noto Sans Arabic", label: "Noto Sans Arabic", hint: "Arabic + Latin" },
  { id: "Vazirmatn", label: "Vazirmatn", hint: "Arabic + Latin, modern" },
  { id: "Noto Naskh Arabic", label: "Noto Naskh Arabic", hint: "Traditional Naskh" },
  { id: "Droid Arabic Kufi", label: "Droid Arabic Kufi", hint: "Display Kufi" },
  { id: "Inter", label: "Inter", hint: "Latin only" },
];

/** ASS PlayRes pixel size behind each size pill. */
const FONT_SIZE_LABELS: Record<string, string> = {
  sm: "76",
  base: "94",
  lg: "110",
  xl: "132",
};

export const CaptionsTabContent: React.FC<CaptionsTabContentProps> = ({
  options,
  onUpdateOptions,
}) => {
  return (
    <div className="space-y-5 text-xs select-none" data-testid="captions-tab-content">
      {/* Section Title */}
      <h3 className="text-sm font-bold text-white tracking-tight">Caption Style</h3>

      {/* 1. Style Presets */}
      <div className="space-y-2">
        <label className="text-slate-300 font-semibold block flex items-center space-x-1.5">
          <Sparkles className="h-3.5 w-3.5 text-laqta-200" />
          <span>Style Preset</span>
        </label>
        <div className="grid grid-cols-2 gap-2">
          {(
            [
              { id: "neon-glow", label: "Neon Glow" },
              { id: "minimalist", label: "Minimalist" },
              { id: "bold-outline", label: "Bold Outline" },
              { id: "cyberpunk", label: "Cyberpunk" },
            ] as const
          ).map((preset) => {
            const isSelected = options.preset === preset.id;
            return (
              <button
                key={preset.id}
                type="button"
                onClick={() =>
                  onUpdateOptions({
                    preset: preset.id as CaptionPreset,
                    highlightColor:
                      preset.id === "cyberpunk"
                        ? "#FACC15"
                        : preset.id === "minimalist"
                          ? "#FFFFFF"
                          : "#00F2FE",
                  })
                }
                className={`p-2.5 rounded-xl border text-left transition-all ${
                  isSelected
                    ? "bg-laqta-900/70 border-laqta-500/60 text-white shadow-neon-purple/40"
                    : "bg-obsidian-950 border-slate-800 text-slate-400 hover:text-white hover:border-slate-700"
                }`}
                data-testid={`preset-btn-${preset.id}`}
              >
                <span className="font-bold block text-[11px]">{preset.label}</span>
                <span className="text-[9px] text-slate-400">
                  {preset.id === "neon-glow" ? "High energy punchline" : "Clean subtitle"}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* 2. Typography & Font Controls */}
      <div className="space-y-3 p-3 rounded-xl bg-obsidian-950/70 border border-slate-800/80">
        <label className="text-slate-300 font-semibold flex items-center gap-1.5">
          <Type className="h-3.5 w-3.5 text-laqta-200" aria-hidden="true" />
          <span>Typography</span>
        </label>

        {/* Font Family */}
        <div className="space-y-1">
          <span className="text-slate-400 text-[10px]">Font Family</span>
          <select
            value={options.fontFamily}
            onChange={(e) => onUpdateOptions({ fontFamily: e.target.value })}
            className="w-full px-2.5 py-2 rounded-lg bg-slate-900 border border-slate-800 text-slate-200 focus:outline-none focus:border-cyan-400 text-xs"
            data-testid="font-family-select"
          >
            {FONT_FAMILIES.map((font) => (
              <option key={font.id} value={font.id}>
                {font.label} — {font.hint}
              </option>
            ))}
          </select>
        </div>

        {/* Font Size Pills */}
        <div className="space-y-1">
          <span className="text-slate-400 text-[10px]">Font Size</span>
          <div className="grid grid-cols-4 gap-1.5">
            {(["sm", "base", "lg", "xl"] as const).map((size) => (
              <button
                key={size}
                type="button"
                onClick={() => onUpdateOptions({ fontSize: size })}
                aria-pressed={options.fontSize === size}
                className={`py-1.5 rounded-lg border text-center font-mono font-semibold text-[10px] uppercase transition focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 cursor-pointer ${
                  options.fontSize === size
                    ? "bg-laqta-900/70 border-laqta-500/60 text-white shadow-sm"
                    : "bg-slate-900/60 border-slate-800 text-slate-400 hover:text-white"
                }`}
                data-testid={`font-size-${size}`}
              >
                {size}
                <span className="block text-[9px] font-normal opacity-70">
                  {FONT_SIZE_LABELS[size]}px
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* 3. Position Picker */}
      <div className="space-y-2">
        <label className="text-slate-300 font-semibold block flex items-center space-x-1.5">
          <AlignVerticalJustifyCenter className="h-3.5 w-3.5 text-slate-400" />
          <span>Vertical Position</span>
        </label>
        <div className="grid grid-cols-3 gap-2">
          {(["top", "middle", "bottom"] as const).map((pos) => (
            <button
              key={pos}
              type="button"
              onClick={() => onUpdateOptions({ position: pos })}
              className={`py-1.5 rounded-xl border text-center font-medium capitalize text-[11px] transition ${
                options.position === pos
                  ? "bg-laqta-900/70 border-laqta-500/60 text-white shadow-sm"
                  : "bg-obsidian-950 border-slate-800 text-slate-400 hover:text-white hover:border-slate-700"
              }`}
              data-testid={`pos-btn-${pos}`}
            >
              {pos}
            </button>
          ))}
        </div>
      </div>

      {/* 4. Highlight Color Swatches */}
      <div className="space-y-2 p-3 rounded-xl bg-obsidian-950/70 border border-slate-800/80">
        <label className="text-slate-300 font-semibold flex items-center space-x-1.5">
          <Palette className="h-3.5 w-3.5 text-laqta-200" />
          <span>Punchline Highlight Color</span>
        </label>
        <div className="flex items-center space-x-2 pt-1">
          {COLOR_SWATCHES.map((swatch) => {
            const isSelected = options.highlightColor.toLowerCase() === swatch.color.toLowerCase();
            return (
              <button
                key={swatch.color}
                type="button"
                onClick={() => onUpdateOptions({ highlightColor: swatch.color })}
                className={`h-7 w-7 rounded-full transition-transform border-2 relative flex items-center justify-center ${
                  isSelected
                    ? "scale-110 border-white shadow-neon-cyan"
                    : "border-transparent hover:scale-105"
                }`}
                style={{ backgroundColor: swatch.color }}
                title={swatch.label}
                data-testid={`color-swatch-${swatch.label.toLowerCase().replace(/\s+/g, "-")}`}
              >
                {isSelected && <div className="h-2 w-2 rounded-full bg-black/60" />}
              </button>
            );
          })}
        </div>
      </div>

      {/* 5. Word-by-Word Karaoke Animation Toggle */}
      <div className="p-3 rounded-xl bg-obsidian-950/70 border border-slate-800/80 flex items-center justify-between gap-3">
        <div className="space-y-0.5 pr-2 min-w-0">
          <div className="flex items-center gap-1.5 text-white font-semibold">
            <Wand2 className="h-3.5 w-3.5 text-laqta-200" aria-hidden="true" />
            <span>Karaoke Word Sync</span>
          </div>
          <p className="text-[10px] text-slate-400 leading-snug">
            Re-times the selected clip locally so each word lights up as it is spoken
          </p>
        </div>
        <Switch
          checked={options.karaokeSync}
          onChange={(karaokeSync) => onUpdateOptions({ karaokeSync })}
          label="Karaoke Word Sync"
          testId="karaoke-sync-toggle"
        />
      </div>
    </div>
  );
};
