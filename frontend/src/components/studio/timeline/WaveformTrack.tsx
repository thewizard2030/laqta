import React, { useRef, useState } from "react";
import { formatMsAsClock } from "../../../lib/i18n/bidi";

interface WaveformTrackProps {
  currentTimeSec: number;
  durationSec: number;
  onSeek: (sec: number) => void;
  zoom: number;
  activeClipWindow?: { startSec: number; endSec: number } | null;
}

export const WaveformTrack: React.FC<WaveformTrackProps> = ({
  currentTimeSec,
  durationSec,
  onSeek,
  zoom,
  activeClipWindow,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const safeDuration = Math.max(1, durationSec);
  const progressPercent = Math.min(100, Math.max(0, (currentTimeSec / safeDuration) * 100));

  // Generate 80 waveform peak bars with organic speech dynamics
  const barCount = 80;
  const waveformBars = Array.from({ length: barCount }, (_, i) => {
    // Simulate vocal pauses and speech burst peaks
    const phase = (i % 8) / 8;
    const isPause = i % 15 === 0 || i % 23 === 0;
    const height = isPause
      ? 15
      : Math.min(95, Math.max(20, Math.round(Math.sin(phase * Math.PI) * 75 + ((i * 13) % 25))));
    return height;
  });

  const calculateTimeFromEvent = (clientX: number): number => {
    const container = containerRef.current;
    if (!container) return 0;
    const rect = container.getBoundingClientRect();
    const offsetX = Math.max(0, Math.min(rect.width, clientX - rect.left));
    const ratio = offsetX / rect.width;
    return ratio * safeDuration;
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    setIsDragging(true);
    const newSec = calculateTimeFromEvent(e.clientX);
    onSeek(newSec);

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const draggedSec = calculateTimeFromEvent(moveEvent.clientX);
      onSeek(draggedSec);
    };

    const handleMouseUp = () => {
      setIsDragging(false);
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
  };

  const activeStartPercent = activeClipWindow
    ? Math.max(0, Math.min(100, (activeClipWindow.startSec / safeDuration) * 100))
    : 0;
  const activeEndPercent = activeClipWindow
    ? Math.max(0, Math.min(100, (activeClipWindow.endSec / safeDuration) * 100))
    : 100;

  return (
    <div
      ref={containerRef}
      onMouseDown={handleMouseDown}
      className="relative h-12 bg-obsidian-950/90 rounded-xl border border-slate-800/80 overflow-hidden cursor-pointer select-none flex items-center px-1"
      data-testid="waveform-track"
    >
      {/* Waveform Amplitude Peaks */}
      <div
        className="flex items-center justify-between w-full h-full space-x-0.5"
        style={{ minWidth: `${100 * zoom}%` }}
      >
        {waveformBars.map((height, i) => {
          const barPercent = (i / barCount) * 100;
          const isInActiveClip = barPercent >= activeStartPercent && barPercent <= activeEndPercent;

          return (
            <div
              key={i}
              className={`flex-1 rounded-full transition-all ${
                isInActiveClip
                  ? "bg-gradient-to-t from-laqta-600 via-laqta-400 to-cyan-400 opacity-90"
                  : "bg-slate-700/50 opacity-40 hover:opacity-70"
              }`}
              style={{ height: `${height}%` }}
            />
          );
        })}
      </div>

      {/* Draggable Neon Cyan Playhead Scrubber */}
      <div
        className="absolute top-0 bottom-0 pointer-events-none z-30 transition-transform duration-75"
        style={{ left: `${progressPercent}%` }}
        data-testid="timeline-playhead"
      >
        {/* Playhead Top Diamond Handle */}
        <div className="absolute -top-1 -translate-x-1/2 h-3 w-3 rotate-45 bg-neon-cyan shadow-neon-cyan rounded-xs" />

        {/* Playhead Vertical Line */}
        <div className="h-full w-0.5 -translate-x-1/2 bg-neon-cyan shadow-[0_0_10px_rgba(0,242,254,0.9)]" />

        {/* Hover/Drag Floating Timecode */}
        {isDragging && (
          <div className="absolute -top-7 -translate-x-1/2 px-1.5 py-0.5 rounded bg-obsidian-950 text-neon-cyan text-[10px] font-mono font-bold border border-cyan-500/50 shadow-md">
            {formatMsAsClock(Math.round(currentTimeSec * 1000))}
          </div>
        )}
      </div>
    </div>
  );
};
