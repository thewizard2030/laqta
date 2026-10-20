import React from "react";
import { MessageSquare } from "lucide-react";
import { TranscriptSegment } from "../../../types/transcription";
import { BidiText } from "../../../lib/i18n/BidiText";

interface SubtitleBlocksTrackProps {
  segments?: TranscriptSegment[];
  durationSec: number;
  zoom: number;
  activeClipWindow?: { startSec: number; endSec: number } | null;
  onSelectSegment?: (segment: TranscriptSegment) => void;
}

export const SubtitleBlocksTrack: React.FC<SubtitleBlocksTrackProps> = ({
  segments = [],
  durationSec,
  zoom,
  activeClipWindow,
  onSelectSegment,
}) => {
  const safeDuration = Math.max(1, durationSec);

  // If no transcript segments, generate visual blocks aligned with active clip
  const displaySegments: TranscriptSegment[] =
    segments.length > 0
      ? segments
      : [
          {
            id: "sim_1",
            start: activeClipWindow?.startSec ?? 0,
            end: (activeClipWindow?.startSec ?? 0) + 12,
            text: "القاعدة الوحيدة للحرية المالية",
          },
          {
            id: "sim_2",
            start: (activeClipWindow?.startSec ?? 0) + 12,
            end: activeClipWindow?.endSec ?? Math.min(30, safeDuration),
            text: "كيف تبني جمهور حقيقي",
          },
        ];

  return (
    <div
      className="relative h-8 bg-obsidian-950/80 rounded-xl border border-slate-800/80 overflow-hidden select-none"
      data-testid="subtitle-blocks-track"
    >
      <div className="relative h-full w-full" style={{ minWidth: `${100 * zoom}%` }}>
        {displaySegments.map((seg) => {
          const leftPercent = Math.max(0, Math.min(100, (seg.start / safeDuration) * 100));
          const rightPercent = Math.max(0, Math.min(100, (seg.end / safeDuration) * 100));
          const widthPercent = Math.max(1, rightPercent - leftPercent);

          const isInsideClip =
            activeClipWindow &&
            seg.end > activeClipWindow.startSec &&
            seg.start < activeClipWindow.endSec;

          return (
            <div
              key={seg.id}
              onClick={() => onSelectSegment && onSelectSegment(seg)}
              className={`absolute top-1 bottom-1 px-2 rounded-lg border text-[10px] font-medium flex items-center justify-between truncate cursor-pointer transition-all duration-150 ${
                isInsideClip
                  ? "bg-gradient-to-r from-laqta-900/90 to-laqta-950/90 text-white border-laqta-600/60 shadow-[0_0_8px_rgba(0,242,254,0.3)] hover:border-cyan-400"
                  : "bg-slate-900/60 text-slate-400 border-slate-800 hover:border-slate-700 hover:text-slate-300"
              }`}
              style={{
                left: `${leftPercent}%`,
                width: `${widthPercent}%`,
              }}
              title={seg.text}
              data-testid={`subtitle-block-${seg.id}`}
            >
              <span className="truncate pr-1">
                <BidiText text={seg.text} />
              </span>
              <MessageSquare className="h-2.5 w-2.5 opacity-50 flex-shrink-0" />
            </div>
          );
        })}
      </div>
    </div>
  );
};
