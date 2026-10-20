import React from "react";
import { TranscriptSegment, WordTiming } from "../../../types/transcription";
import { detectTextDirection } from "../../../lib/i18n/bidi";
import { cleanDisplayText } from "../../../lib/format";

export interface CaptionStyleConfig {
  position?: "bottom" | "middle" | "top";
  fontSize?: "sm" | "base" | "lg" | "xl";
  highlightColor?: string; // hex or tailwind class
  karaokeSync?: boolean;
  preset?: "neon-glow" | "minimalist" | "bold-outline" | "cyberpunk";
  fontFamily?: string;
  textColor?: string;
}

interface LiveKaraokeCaptionProps {
  currentTimeSec: number;
  segments?: TranscriptSegment[];
  fallbackText?: string;
  styleConfig?: CaptionStyleConfig;
}

export const LiveKaraokeCaption: React.FC<LiveKaraokeCaptionProps> = ({
  currentTimeSec,
  segments = [],
  fallbackText = "",
  styleConfig = {},
}) => {
  const {
    position = "bottom",
    fontSize = "lg",
    highlightColor = "#00F2FE",
    karaokeSync = true,
    preset = "neon-glow",
    fontFamily,
    textColor,
  } = styleConfig;

  // Find active segment matching the current playback timecode
  const activeSegment = segments.find(
    (seg) => currentTimeSec >= seg.start && currentTimeSec <= seg.end,
  );

  const positionClasses = {
    top: "top-8",
    middle: "top-1/2 -translate-y-1/2",
    bottom: "bottom-14",
  };

  const fontSizeClasses = {
    sm: "text-sm sm:text-base",
    base: "text-base sm:text-lg",
    lg: "text-lg sm:text-xl",
    xl: "text-xl sm:text-2xl",
  };

  // If active segment has word timings, perform granular word-level karaoke sync
  if (activeSegment && activeSegment.words && activeSegment.words.length > 0 && karaokeSync) {
    const rawClean = cleanDisplayText(activeSegment.text);
    if (!rawClean) return null;
    const isRtl = detectTextDirection(rawClean) === "rtl";

    return (
      <div
        className={`absolute left-4 right-4 ${positionClasses[position]} z-20 flex justify-center text-center pointer-events-none select-none`}
        data-testid="live-karaoke-caption"
      >
        <div
          dir={isRtl ? "rtl" : "ltr"}
          style={fontFamily ? { fontFamily } : undefined}
          className={`flex flex-wrap items-center justify-center gap-1.5 px-3.5 py-2 rounded-2xl max-w-sm font-bold tracking-tight transition-all ${fontSizeClasses[fontSize]} ${
            preset === "cyberpunk"
              ? "bg-yellow-400 text-black border-2 border-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]"
              : preset === "bold-outline"
                ? "bg-black/40 backdrop-blur-sm border border-slate-700/60 shadow-2xl"
                : preset === "minimalist"
                  ? "bg-black/60 backdrop-blur-sm border border-white/10 shadow-lg text-white"
                  : "bg-obsidian-950/80 backdrop-blur-md border border-cyan-500/30 shadow-[0_0_20px_rgba(0,242,254,0.25)]"
          }`}
        >
          {activeSegment.words.map((w: WordTiming, index: number) => {
            const isSpoken = currentTimeSec >= w.start && currentTimeSec <= w.end;
            const isPast = currentTimeSec > w.end;
            const wordClean = cleanDisplayText(w.word);
            if (!wordClean) return null;

            if (isSpoken) {
              return (
                <span
                  key={index}
                  className="px-2 py-0.5 rounded-lg text-obsidian-950 font-black shadow-[0_0_15px_rgba(0,242,254,0.7)] scale-105 transition-all duration-100"
                  style={{ backgroundColor: highlightColor }}
                  data-testid="karaoke-active-word"
                >
                  {wordClean}
                </span>
              );
            }

            return (
              <span
                key={index}
                style={textColor ? { color: textColor } : undefined}
                className={`transition-colors duration-100 ${
                  isPast
                    ? "text-white drop-shadow-[0_2px_4px_rgba(0,0,0,0.8)]"
                    : "text-slate-300 drop-shadow"
                }`}
              >
                {wordClean}
              </span>
            );
          })}
        </div>
      </div>
    );
  }

  // Segment-level or Fallback Hook Rendering
  const rawText = activeSegment ? activeSegment.text : fallbackText;
  const displayText = cleanDisplayText(rawText);
  if (!displayText) {
    return null;
  }

  const isRtl = detectTextDirection(displayText) === "rtl";
  const words = displayText.trim().split(/\s+/);

  // Split into base phrase and highlighted punchline word/phrase
  const baseWords = words.length > 2 ? words.slice(0, words.length - 2).join(" ") : words[0] || "";
  const highlightedWords =
    words.length > 2 ? words.slice(words.length - 2).join(" ") : words.slice(1).join(" ") || "";

  return (
    <div
      className={`absolute left-4 right-4 ${positionClasses[position]} z-20 flex justify-center text-center pointer-events-none select-none`}
      data-testid="live-karaoke-caption"
    >
      <div
        dir={isRtl ? "rtl" : "ltr"}
        style={fontFamily ? { fontFamily } : undefined}
        className={`flex flex-wrap items-center justify-center gap-2 px-3.5 py-2 rounded-2xl max-w-sm font-bold transition-all ${fontSizeClasses[fontSize]} ${
          preset === "cyberpunk"
            ? "bg-yellow-400 text-black border-2 border-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]"
            : preset === "bold-outline"
              ? "bg-black/50 backdrop-blur-sm border border-slate-700/60 shadow-2xl"
              : preset === "minimalist"
                ? "bg-black/60 backdrop-blur-sm border border-white/10 shadow-lg text-white"
                : "bg-obsidian-950/80 backdrop-blur-md border border-cyan-500/30 shadow-[0_0_20px_rgba(0,242,254,0.25)]"
        }`}
      >
        {baseWords && (
          <span
            style={textColor ? { color: textColor } : undefined}
            className="text-white drop-shadow-[0_2px_8px_rgba(0,0,0,0.9)]"
          >
            {baseWords}
          </span>
        )}
        {highlightedWords && (
          <span
            className="px-2 py-0.5 rounded-lg text-obsidian-950 font-black shadow-[0_0_15px_rgba(0,242,254,0.7)]"
            style={{ backgroundColor: highlightColor }}
            data-testid="karaoke-highlighted-phrase"
          >
            {highlightedWords}
          </span>
        )}
      </div>
    </div>
  );
};
