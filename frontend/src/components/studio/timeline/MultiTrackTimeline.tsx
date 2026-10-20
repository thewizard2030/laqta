import React, { useRef, useState } from "react";
import {
  Film,
  Mic,
  MessageSquare,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Sliders,
  Clock,
  Scissors,
} from "lucide-react";
import { TranscriptSegment } from "../../../types/transcription";
import { formatMsAsClock } from "../../../lib/i18n/bidi";
import { FilmstripTrack } from "./FilmstripTrack";
import { WaveformTrack } from "./WaveformTrack";
import { SubtitleBlocksTrack } from "./SubtitleBlocksTrack";

interface MultiTrackTimelineProps {
  currentTimeSec: number;
  durationSec: number;
  onSeek: (sec: number) => void;
  activeClipWindow?: { startSec: number; endSec: number } | null;
  segments?: TranscriptSegment[];
  onSelectSegment?: (segment: TranscriptSegment) => void;
  zoomPrefix?: string;
}

/**
 * Candidate ruler steps. The first one that keeps the number of visible
 * labels under `MAX_RULER_LABELS` wins, so a 23-minute video does not
 * render 280 overlapping tick labels.
 */
const RULER_STEPS = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600];
const MAX_RULER_LABELS = 12;

export const MultiTrackTimeline: React.FC<MultiTrackTimelineProps> = ({
  currentTimeSec,
  durationSec,
  onSeek,
  activeClipWindow,
  segments = [],
  onSelectSegment,
  zoomPrefix = "",
}) => {
  const [zoom, setZoom] = useState<number>(1); // 1 = 100%, 1.5, 2
  const rulerRef = useRef<HTMLDivElement>(null);

  const safeDuration = Math.max(1, durationSec);

  // Adaptive time ruler: pick a step that keeps the labels readable.
  const tickStep =
    RULER_STEPS.find((step) => safeDuration / step <= MAX_RULER_LABELS) ??
    RULER_STEPS[RULER_STEPS.length - 1];

  const timeTicks = React.useMemo(() => {
    const ticks: { sec: number; label: string; percent: number }[] = [];
    for (let sec = 0; sec <= safeDuration; sec += tickStep) {
      ticks.push({
        sec,
        label: formatMsAsClock(sec * 1000),
        percent: (sec / safeDuration) * 100,
      });
    }
    // Always anchor the last label to the very end of the media.
    const last = ticks[ticks.length - 1];
    if (!last || safeDuration - last.sec > tickStep * 0.6) {
      ticks.push({
        sec: safeDuration,
        label: formatMsAsClock(safeDuration * 1000),
        percent: 100,
      });
    }
    return ticks;
  }, [safeDuration, tickStep]);

  const handleZoomIn = () => {
    setZoom((prev) => Math.min(2.5, prev + 0.25));
  };

  const handleZoomOut = () => {
    setZoom((prev) => Math.max(1, prev - 0.25));
  };

  const handleZoomReset = () => {
    setZoom(1);
  };

  /** Click the ruler to jump the playhead. */
  const handleRulerClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const ruler = rulerRef.current;
    if (!ruler) return;
    const rect = ruler.getBoundingClientRect();
    if (rect.width === 0) return;
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    onSeek(ratio * safeDuration);
  };

  const trackLabelClass = "w-[76px] shrink-0 flex items-center gap-1.5 text-[11px] text-slate-400";

  return (
    <div
      className="rounded-2xl border border-slate-800/80 bg-obsidian-900/70 p-3.5 space-y-2.5 backdrop-blur-md select-none shadow-panel"
      data-testid="multi-track-timeline"
    >
      {/* Timeline Controls & Timecode Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-slate-800/80 text-xs">
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="font-bold text-white tracking-tight flex items-center gap-1.5">
            <Sliders className="h-4 w-4 text-laqta-200" aria-hidden="true" />
            <span>Multi-Track Timeline</span>
          </span>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-900/80 text-slate-300 border border-slate-700/60">
            Interactive Editor
          </span>

          {/* Active clip range — the region that will be rendered. */}
          {activeClipWindow && (
            <span
              className="inline-flex items-center gap-1.5 text-[10px] font-mono px-2 py-0.5 rounded-full bg-laqta-950/70 text-laqta-200 border border-laqta-800/50"
              title="Range of the clip that will be rendered"
            >
              <Scissors className="h-2.5 w-2.5" aria-hidden="true" />
              {formatMsAsClock(Math.round(activeClipWindow.startSec * 1000))} –{" "}
              {formatMsAsClock(Math.round(activeClipWindow.endSec * 1000))}
            </span>
          )}
        </div>

        {/* Current Timecode & Zoom Tools */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 font-mono text-[11px] bg-obsidian-950 px-2.5 py-1 rounded-lg border border-slate-800">
            <Clock className="h-3 w-3 text-laqta-200" aria-hidden="true" />
            <span className="text-white font-semibold">
              {formatMsAsClock(Math.round(currentTimeSec * 1000))}
            </span>
            <span className="text-slate-500" aria-hidden="true">
              /
            </span>
            <span className="text-slate-400">
              {formatMsAsClock(Math.round(safeDuration * 1000))}
            </span>
          </div>

          <div className="flex items-center gap-1 bg-obsidian-950 p-0.5 rounded-lg border border-slate-800">
            <button
              onClick={handleZoomOut}
              disabled={zoom <= 1}
              className="p-1 rounded text-slate-400 hover:text-white disabled:opacity-40 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 cursor-pointer"
              title="Zoom out"
              aria-label="Zoom out"
              data-testid="zoom-out-btn"
            >
              <ZoomOut className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
            <span className="text-[10px] font-mono px-1 text-slate-400 min-w-[52px] text-center">
              {zoomPrefix}
              {Math.round(zoom * 100)}%
            </span>
            <button
              onClick={handleZoomIn}
              disabled={zoom >= 2.5}
              className="p-1 rounded text-slate-400 hover:text-white disabled:opacity-40 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 cursor-pointer"
              title="Zoom in"
              aria-label="Zoom in"
              data-testid="zoom-in-btn"
            >
              <ZoomIn className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
            <button
              onClick={handleZoomReset}
              className="p-1 rounded text-slate-400 hover:text-white transition focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 cursor-pointer"
              title="Fit to screen"
              aria-label="Fit timeline to screen"
              data-testid="zoom-reset-btn"
            >
              <Maximize2 className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </div>
        </div>
      </div>

      {/* Main Track Workspace */}
      <div className="space-y-1.5">
        {/* Time Ruler Bar — click to seek */}
        <div
          ref={rulerRef}
          onClick={handleRulerClick}
          className="relative h-4 w-full bg-obsidian-950/90 rounded-md border border-slate-800 px-2 overflow-hidden flex items-center cursor-pointer"
          role="presentation"
        >
          <div className="relative h-full w-full" style={{ minWidth: `${100 * zoom}%` }}>
            {timeTicks.map((tick, idx) => (
              <div
                key={idx}
                className="absolute top-0 bottom-0 flex flex-col justify-between"
                style={{ left: `${tick.percent}%` }}
              >
                <span className="text-[9px] font-mono text-slate-500 -translate-x-1/2 whitespace-nowrap">
                  {tick.label}
                </span>
                <div className="h-1.5 w-px bg-slate-700" />
              </div>
            ))}
          </div>
        </div>

        {/* Track 1: Video Filmstrip */}
        <div className="flex items-center space-x-2">
          <div className={trackLabelClass}>
            <Film className="h-3.5 w-3.5 text-laqta-300" aria-hidden="true" />
            <span>Video</span>
          </div>
          <div className="flex-1 min-w-0">
            <FilmstripTrack
              durationSec={safeDuration}
              zoom={zoom}
              activeClipWindow={activeClipWindow}
            />
          </div>
        </div>

        {/* Track 2: Audio Amplitude Waveform with Playhead */}
        <div className="flex items-center space-x-2">
          <div className={trackLabelClass}>
            <Mic className="h-3.5 w-3.5 text-slate-400" aria-hidden="true" />
            <span>Audio</span>
          </div>
          <div className="flex-1 min-w-0">
            <WaveformTrack
              currentTimeSec={currentTimeSec}
              durationSec={safeDuration}
              onSeek={onSeek}
              zoom={zoom}
              activeClipWindow={activeClipWindow}
            />
          </div>
        </div>

        {/* Track 3: Subtitle / Candidate Clip Blocks */}
        <div className="flex items-center space-x-2">
          <div className={trackLabelClass}>
            <MessageSquare className="h-3.5 w-3.5 text-amber-400" aria-hidden="true" />
            <span>Captions</span>
          </div>
          <div className="flex-1 min-w-0">
            <SubtitleBlocksTrack
              segments={segments}
              durationSec={safeDuration}
              zoom={zoom}
              activeClipWindow={activeClipWindow}
              onSelectSegment={onSelectSegment}
            />
          </div>
        </div>
      </div>
    </div>
  );
};
