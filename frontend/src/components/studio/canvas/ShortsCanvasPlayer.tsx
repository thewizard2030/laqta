import React, { useRef, useEffect, useState } from "react";
import { UserCheck, Sparkles, Smartphone, Monitor, Square } from "lucide-react";
import { TranscriptSegment } from "../../../types/transcription";
import { LiveKaraokeCaption, CaptionStyleConfig } from "./LiveKaraokeCaption";
import { PlayerControlsBar } from "./PlayerControlsBar";
import { LaqtaMark } from "../../ui/LaqtaMark";

export type AspectRatioType = "9:16" | "16:9" | "1:1";

interface ShortsCanvasPlayerProps {
  mediaUrl?: string | null;
  mediaTitle?: string;
  aspectRatio: AspectRatioType;
  onChangeAspectRatio: (ratio: AspectRatioType) => void;
  showSpeakerGuide?: boolean;
  onToggleSpeakerGuide?: () => void;
  segments?: TranscriptSegment[];
  fallbackText?: string;
  captionStyle?: CaptionStyleConfig;
  currentTimeSec: number;
  durationSec: number;
  isPlaying: boolean;
  onTogglePlay: () => void;
  onSeek: (sec: number) => void;
  onTimeUpdate?: (sec: number) => void;
  clipWindow?: { startSec: number; endSec: number } | null;
}

export const ShortsCanvasPlayer: React.FC<ShortsCanvasPlayerProps> = ({
  mediaUrl,
  mediaTitle = "Laqta Short Preview",
  aspectRatio,
  onChangeAspectRatio,
  showSpeakerGuide = true,
  onToggleSpeakerGuide,
  segments = [],
  fallbackText = "",
  captionStyle,
  currentTimeSec,
  durationSec,
  isPlaying,
  onTogglePlay,
  onSeek,
  onTimeUpdate,
  clipWindow,
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [isMuted, setIsMuted] = useState<boolean>(false);
  const [isLooping, setIsLooping] = useState<boolean>(true);
  const [scrubberMode, setScrubberMode] = useState<"clip" | "full">("clip");

  // When the clip window changes, default the scrubber back to clip mode.
  // The key is stable, so a new object with the same range does not reset it.
  // The reset is applied during render (React's documented pattern for a
  // prop change) rather than in an effect.
  const clipWindowKey = clipWindow ? `${clipWindow.startSec}-${clipWindow.endSec}` : null;
  const [previousClipWindowKey, setPreviousClipWindowKey] = useState(clipWindowKey);
  if (previousClipWindowKey !== clipWindowKey) {
    setPreviousClipWindowKey(clipWindowKey);
    if (clipWindowKey) {
      setScrubberMode("clip");
    }
  }

  // Synchronize external play/pause state with video element
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    if (isPlaying && video.paused) {
      video.play().catch(() => {});
    } else if (!isPlaying && !video.paused) {
      video.pause();
    }
  }, [isPlaying]);

  // Handle external seek jumps
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    if (Math.abs(video.currentTime - currentTimeSec) > 0.4) {
      video.currentTime = currentTimeSec;
    }
  }, [currentTimeSec]);

  // Synchronize mute state
  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.muted = isMuted;
    }
  }, [isMuted]);

  const handleVideoTimeUpdate = () => {
    const video = videoRef.current;
    if (!video) return;

    const current = video.currentTime;

    // In clip scrubber mode with auto-loop, loop back when reaching the end of the clip
    if (clipWindow && scrubberMode === "clip") {
      if (current >= clipWindow.endSec) {
        if (isLooping) {
          video.currentTime = clipWindow.startSec;
          onTimeUpdate?.(clipWindow.startSec);
          return;
        } else {
          video.pause();
          onTogglePlay();
          return;
        }
      }
    }

    if (onTimeUpdate) {
      onTimeUpdate(current);
    }
  };

  /**
   * Frame sizing.
   *
   * The canvas must always keep its true aspect ratio: a squashed preview
   * makes the creator judge the wrong framing. Portrait and square frames
   * are driven by the available *height* (they are the tall ones), while
   * widescreen is driven by the available *width*. `shrink-0` stops the
   * flex container from compressing the frame when the column is short.
   */
  const aspectRatioContainerClasses: Record<AspectRatioType, string> = {
    "9:16": "h-full w-auto aspect-[9/16] max-w-full",
    "16:9": "w-full h-auto aspect-[16/9] max-h-full",
    "1:1": "h-full w-auto aspect-square max-w-full",
  };

  const ratioButtonClass = (ratio: AspectRatioType) =>
    `flex items-center gap-1 px-2.5 py-1 rounded-lg font-medium transition focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 ${
      aspectRatio === ratio
        ? "bg-laqta-900/70 text-laqta-100 border border-laqta-600/50 shadow-sm"
        : "text-slate-400 hover:text-white"
    }`;

  return (
    <div
      className="flex flex-col items-center justify-center h-full min-h-0 gap-3 sm:gap-4 p-2 sm:p-3 select-none"
      data-testid="shorts-canvas-player"
    >
      {/* Aspect Ratio Selector & Overlay Toggles Bar */}
      <div className="flex items-center justify-between w-full max-w-[420px] px-1 text-xs shrink-0">
        <div
          className="flex items-center gap-1 bg-obsidian-950/80 p-1 rounded-xl border border-slate-800"
          role="group"
          aria-label="Preview aspect ratio"
        >
          <button
            onClick={() => onChangeAspectRatio("9:16")}
            className={ratioButtonClass("9:16")}
            data-testid="ar-9-16-btn"
            aria-pressed={aspectRatio === "9:16"}
          >
            <Smartphone className="h-3 w-3" aria-hidden="true" />
            <span className="text-[11px]">9:16</span>
          </button>

          <button
            onClick={() => onChangeAspectRatio("1:1")}
            className={ratioButtonClass("1:1")}
            data-testid="ar-1-1-btn"
            aria-pressed={aspectRatio === "1:1"}
          >
            <Square className="h-3 w-3" aria-hidden="true" />
            <span className="text-[11px]">1:1</span>
          </button>

          <button
            onClick={() => onChangeAspectRatio("16:9")}
            className={ratioButtonClass("16:9")}
            data-testid="ar-16-9-btn"
            aria-pressed={aspectRatio === "16:9"}
          >
            <Monitor className="h-3 w-3" aria-hidden="true" />
            <span className="text-[11px]">16:9</span>
          </button>
        </div>

        {onToggleSpeakerGuide && (
          <button
            onClick={onToggleSpeakerGuide}
            className={`p-1.5 rounded-xl border transition focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 ${
              showSpeakerGuide
                ? "bg-laqta-900/70 text-laqta-100 border-laqta-600/50"
                : "bg-obsidian-900 text-slate-400 border-slate-800 hover:text-white"
            }`}
            title="Toggle active speaker framing guide"
            aria-label="Toggle active speaker framing guide"
            aria-pressed={showSpeakerGuide}
            data-testid="speaker-guide-toggle-btn"
          >
            <UserCheck className="h-4 w-4" aria-hidden="true" />
          </button>
        )}
      </div>

      {/* Vertical Phone Canvas / Frame */}
      <div className="flex-1 min-h-0 w-full flex items-center justify-center relative">
        {/* Stage: the area around the frame is a lit workbench with a faint
            measuring grid, so the preview never floats in a black void. */}
        <div
          aria-hidden="true"
          className="absolute inset-0 rounded-2xl overflow-hidden laqta-stage-grid"
        />
        <div aria-hidden="true" className="absolute inset-0 rounded-2xl laqta-stage-glow" />
        <div
          className={`relative shrink-0 rounded-[28px] overflow-hidden bg-black border-2 border-slate-700/80 shadow-2xl shadow-laqta-950/60 flex items-center justify-center group ${aspectRatioContainerClasses[aspectRatio]}`}
          data-testid="canvas-phone-frame"
        >
          {/* Subtle Phone Notch / Speaker bar */}
          <div className="absolute top-2 left-1/2 -translate-x-1/2 w-16 h-1 rounded-full bg-slate-800/80 z-30 pointer-events-none" />

          {/* Top Watermark Brand Overlay */}
          <div className="absolute top-4 left-4 z-20 flex items-center gap-1.5 pointer-events-none">
            <LaqtaMark size={14} title="" />
            <span className="text-[11px] font-bold text-white/70 tracking-wider">Laqta</span>
          </div>

          {/* Title-safe guide (9:16 only) — shows where text stays readable. */}
          {aspectRatio === "9:16" && (
            <div
              className="absolute inset-x-6 top-20 bottom-24 border border-dashed border-white/15 rounded-xl pointer-events-none z-10"
              data-testid="title-safe-guide"
            >
              <span className="absolute -top-px left-2 -translate-y-1/2 bg-black/60 px-1.5 py-0.5 rounded text-[8px] font-mono uppercase tracking-wider text-white/45">
                Title safe
              </span>
            </div>
          )}

          {/* Active Speaker Crop Guide Overlay */}
          {showSpeakerGuide && aspectRatio === "9:16" && (
            <div
              className="absolute inset-x-8 top-12 bottom-28 border border-dashed border-neon-cyan/40 rounded-2xl pointer-events-none z-10 flex flex-col justify-between p-2"
              data-testid="speaker-guide-overlay"
            >
              <div className="flex items-center gap-1 text-[9px] text-neon-cyan bg-obsidian-950/80 px-1.5 py-0.5 rounded border border-cyan-800/40 w-fit">
                <UserCheck className="h-2.5 w-2.5" aria-hidden="true" />
                <span>Face Track</span>
              </div>
            </div>
          )}

          {/* Video Element or Gradient Placeholder Studio Pattern */}
          {mediaUrl ? (
            <video
              ref={videoRef}
              src={mediaUrl}
              onTimeUpdate={handleVideoTimeUpdate}
              onClick={onTogglePlay}
              className="h-full w-full object-cover cursor-pointer"
              data-testid="shorts-video-element"
              playsInline
            />
          ) : (
            <div
              onClick={onTogglePlay}
              className="h-full w-full bg-linear-to-b from-slate-900 via-obsidian-950 to-slate-950 flex flex-col items-center justify-center p-6 text-center cursor-pointer relative"
              data-testid="shorts-video-placeholder"
            >
              <div className="h-16 w-16 rounded-2xl bg-laqta-950/50 border border-laqta-700/50 flex items-center justify-center text-laqta-200 mb-3 shadow-neon-purple">
                <Sparkles className="h-8 w-8" aria-hidden="true" />
              </div>
              <p className="text-xs font-semibold text-white">{mediaTitle}</p>
              <p className="text-[11px] text-slate-400 mt-1">9:16 Portrait Canvas Preview</p>
            </div>
          )}

          {/* Dynamic Live Karaoke Captions Overlay */}
          <LiveKaraokeCaption
            currentTimeSec={currentTimeSec}
            segments={segments}
            fallbackText={fallbackText}
            styleConfig={captionStyle}
          />
        </div>
      </div>

      {/* Scrubber and Playback Controls Bar */}
      <div className="w-full max-w-[420px] shrink-0">
        <PlayerControlsBar
          isPlaying={isPlaying}
          onTogglePlay={onTogglePlay}
          currentTimeSec={currentTimeSec}
          durationSec={durationSec}
          onSeek={onSeek}
          isMuted={isMuted}
          onToggleMute={() => setIsMuted((prev) => !prev)}
          isLooping={isLooping}
          onToggleLoop={() => setIsLooping((prev) => !prev)}
          clipWindow={clipWindow}
          scrubberMode={scrubberMode}
          onToggleScrubberMode={() =>
            setScrubberMode((prev) => (prev === "clip" ? "full" : "clip"))
          }
        />
      </div>
    </div>
  );
};
