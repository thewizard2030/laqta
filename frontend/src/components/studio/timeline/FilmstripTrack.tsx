import React from "react";
import { Film } from "lucide-react";

interface FilmstripTrackProps {
  durationSec: number;
  zoom: number; // 1 = 100%, 2 = 200%, etc.
  activeClipWindow?: { startSec: number; endSec: number } | null;
}

/** Upper bound on rendered frames so long videos stay performant. */
const MAX_FRAMES = 48;

export const FilmstripTrack: React.FC<FilmstripTrackProps> = ({
  durationSec,
  zoom,
  activeClipWindow,
}) => {
  const safeDuration = Math.max(1, durationSec);
  // One frame every ~5 seconds, capped so a 2-hour video does not render
  // thousands of DOM nodes.
  const frameCount = Math.min(MAX_FRAMES, Math.max(6, Math.ceil(safeDuration / 5)));
  const frames = Array.from({ length: frameCount }, (_, i) => ({
    sec: (i * safeDuration) / frameCount,
    label: `${Math.round((i * safeDuration) / frameCount)}s`,
  }));

  const activeStartPercent = activeClipWindow
    ? Math.max(0, Math.min(100, (activeClipWindow.startSec / safeDuration) * 100))
    : 0;
  const activeEndPercent = activeClipWindow
    ? Math.max(0, Math.min(100, (activeClipWindow.endSec / safeDuration) * 100))
    : 100;
  const activeWidthPercent = Math.max(0, activeEndPercent - activeStartPercent);

  return (
    <div
      className="relative h-10 bg-obsidian-950/80 rounded-xl border border-slate-800/80 overflow-hidden flex items-center select-none"
      data-testid="filmstrip-track"
    >
      {/* Frame Strip Sequence */}
      <div
        className="flex h-full w-full items-center divide-x divide-slate-800/80"
        style={{ minWidth: `${100 * zoom}%` }}
      >
        {frames.map((frame, idx) => (
          <div
            key={idx}
            className="flex-1 h-full bg-gradient-to-br from-slate-900/80 to-obsidian-900 flex flex-col items-center justify-between p-1 relative group"
          >
            <div className="flex items-center opacity-30 group-hover:opacity-80 transition">
              <Film className="h-2.5 w-2.5 text-slate-400" aria-hidden="true" />
            </div>
            <span className="text-[8px] font-mono text-slate-600 group-hover:text-slate-400 transition">
              {frame.label}
            </span>
          </div>
        ))}
      </div>

      {/* Active Candidate Clip Overlay Boundary — the range that gets
          rendered. The numeric range is shown in the timeline header. */}
      {activeClipWindow && (
        <div
          className="absolute top-0 bottom-0 border-2 border-neon-cyan bg-cyan-500/10 rounded-lg pointer-events-none shadow-[0_0_12px_rgba(0,242,254,0.25)] transition-all"
          style={{
            left: `${activeStartPercent}%`,
            width: `${activeWidthPercent}%`,
          }}
          data-testid="active-clip-filmstrip-window"
        />
      )}
    </div>
  );
};
