import React from "react";
import { Play, Pause, Volume2, VolumeX, RotateCcw, Maximize } from "lucide-react";
import { formatMsAsClock } from "../../../lib/i18n/bidi";

interface PlayerControlsBarProps {
  isPlaying: boolean;
  onTogglePlay: () => void;
  currentTimeSec: number;
  durationSec: number;
  onSeek: (timeSec: number) => void;
  isMuted?: boolean;
  onToggleMute?: () => void;
  isLooping?: boolean;
  onToggleLoop?: () => void;
  onFullscreen?: () => void;
  clipWindow?: { startSec: number; endSec: number } | null;
  scrubberMode?: "clip" | "full";
  onToggleScrubberMode?: () => void;
}

export const PlayerControlsBar: React.FC<PlayerControlsBarProps> = ({
  isPlaying,
  onTogglePlay,
  currentTimeSec,
  durationSec,
  onSeek,
  isMuted = false,
  onToggleMute,
  isLooping = false,
  onToggleLoop,
  onFullscreen,
  clipWindow,
  scrubberMode = "clip",
  onToggleScrubberMode,
}) => {
  const isClipActive = Boolean(clipWindow && scrubberMode === "clip");
  const clipDuration = clipWindow ? Math.max(0.1, clipWindow.endSec - clipWindow.startSec) : 30;
  const fullSafeDuration = durationSec > 0 ? durationSec : 30;

  const displayDuration = isClipActive ? clipDuration : fullSafeDuration;
  const displayCurrent = isClipActive
    ? Math.max(0, Math.min(clipDuration, currentTimeSec - (clipWindow?.startSec ?? 0)))
    : currentTimeSec;

  const progressPercent = Math.min(100, Math.max(0, (displayCurrent / displayDuration) * 100));

  const handleScrubberChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseFloat(e.target.value);
    if (isClipActive && clipWindow) {
      onSeek(clipWindow.startSec + val);
    } else {
      onSeek(val);
    }
  };

  return (
    <div
      className="w-full bg-obsidian-950/90 backdrop-blur-md rounded-2xl border border-slate-800/80 p-3 space-y-2.5 select-none"
      data-testid="player-controls-bar"
    >
      {/* Time Scrubber Slider */}
      <div className="relative flex items-center h-4 group">
        <div className="absolute inset-x-0 h-1.5 rounded-full bg-slate-800 overflow-hidden">
          <div
            className="h-full rounded-full laqta-gradient-surface transition-[width] duration-150"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
        <input
          type="range"
          min={0}
          max={displayDuration}
          step={0.05}
          value={displayCurrent}
          onChange={handleScrubberChange}
          aria-label={isClipActive ? "Clip playback position" : "Playback position"}
          className="range-bare relative w-full h-1.5 cursor-pointer focus:outline-none"
          data-testid="player-time-slider"
        />
      </div>

      {/* Control Buttons & Timecode */}
      <div className="flex items-center justify-between text-xs text-slate-300">
        <div className="flex items-center gap-3">
          {/* Play / Pause Primary Button */}
          <button
            onClick={onTogglePlay}
            className="h-9 w-9 rounded-full laqta-gradient-surface hover:brightness-110 text-white flex items-center justify-center shadow-laqta-glow transition-[filter] duration-150 active:scale-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 cursor-pointer"
            aria-label={isPlaying ? "Pause" : "Play"}
            data-testid="play-pause-btn"
          >
            {isPlaying ? (
              <Pause className="h-4 w-4 fill-white" aria-hidden="true" />
            ) : (
              <Play className="h-4 w-4 fill-white ml-0.5" aria-hidden="true" />
            )}
          </button>

          {/* Timecode Clock & Mode Toggle */}
          <div className="flex items-center gap-2">
            <div className="font-mono text-[11px] text-slate-400 flex items-center gap-1">
              <span className="text-white font-semibold">
                {formatMsAsClock(Math.round(displayCurrent * 1000))}
              </span>
              <span aria-hidden="true">/</span>
              <span>{formatMsAsClock(Math.round(displayDuration * 1000))}</span>
            </div>

            {clipWindow && onToggleScrubberMode && (
              <button
                type="button"
                onClick={onToggleScrubberMode}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-obsidian-900 border border-slate-700/80 hover:border-cyan-500/60 transition cursor-pointer"
                title="Toggle scrubber between clip range and full media timeline"
                data-testid="scrubber-mode-toggle"
              >
                <span
                  className={
                    scrubberMode === "clip" ? "text-neon-cyan font-bold" : "text-slate-500"
                  }
                >
                  Clip
                </span>
                <span className="text-slate-600">/</span>
                <span
                  className={
                    scrubberMode === "full" ? "text-neon-cyan font-bold" : "text-slate-500"
                  }
                >
                  Full
                </span>
              </button>
            )}
          </div>
        </div>

        {/* Right Tools: Loop, Volume, Fullscreen */}
        <div className="flex items-center gap-1.5">
          {onToggleLoop && (
            <button
              onClick={onToggleLoop}
              className={`p-1.5 rounded-lg transition focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 cursor-pointer ${
                isLooping
                  ? "text-neon-cyan bg-cyan-950/60 border border-cyan-800/40"
                  : "text-slate-400 hover:text-white hover:bg-slate-800"
              }`}
              title={isLooping ? "Auto-loop enabled" : "Auto-loop disabled"}
              aria-pressed={isLooping}
              data-testid="loop-toggle-btn"
            >
              <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          )}

          {onToggleMute && (
            <button
              onClick={onToggleMute}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 cursor-pointer"
              title={isMuted ? "Unmute" : "Mute"}
              aria-pressed={isMuted}
              data-testid="mute-toggle-btn"
            >
              {isMuted ? (
                <VolumeX className="h-3.5 w-3.5 text-red-400" aria-hidden="true" />
              ) : (
                <Volume2 className="h-3.5 w-3.5" aria-hidden="true" />
              )}
            </button>
          )}

          {onFullscreen && (
            <button
              onClick={onFullscreen}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 cursor-pointer"
              title="Fullscreen Canvas"
              data-testid="player-fullscreen-btn"
            >
              <Maximize className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
