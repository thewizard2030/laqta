import React, { memo, useState } from "react";
import { Clock, Film, Play, Gauge, Check, Zap } from "lucide-react";
import { Candidate } from "../../../types/candidates";
import { formatMsAsClock } from "../../../lib/i18n/bidi";
import { BidiText } from "../../../lib/i18n/BidiText";
import { cleanDisplayText } from "../../../lib/format";
import { generateCandidateThumbnailUrl } from "../../../lib/api/mediaUrl";
import { pickMeaningfulRationale } from "../../../lib/rationale";

interface ClipCardItemProps {
  rank: number;
  candidate: Candidate;
  isSelected: boolean;
  onSelect: (candidate: Candidate) => void;
  /** Real media asset id; when given, a real extracted preview frame is shown. */
  mediaId?: string | null;
  tags?: string[];
  snippetText?: string;
  thumbnailEpoch?: number;
  isRendered?: boolean;
}

const ClipCardItemComponent: React.FC<ClipCardItemProps> = ({
  rank,
  candidate,
  isSelected,
  onSelect,
  mediaId = null,
  tags,
  snippetText,
  thumbnailEpoch = 0,
  isRendered = false,
}) => {
  const [thumbnailFailed, setThumbnailFailed] = useState(false);

  // Reset the "failed" flag when the frame source changes, so a newly
  // generated thumbnail is requested again. Comparing during render is
  // React's documented way to adjust state on a prop change — an effect
  // would render once with the stale value first.
  const thumbnailSource = `${thumbnailEpoch}:${candidate.id}:${mediaId ?? ""}`;
  const [previousThumbnailSource, setPreviousThumbnailSource] = useState(thumbnailSource);
  if (previousThumbnailSource !== thumbnailSource) {
    setPreviousThumbnailSource(thumbnailSource);
    setThumbnailFailed(false);
  }

  const thumbnailUrl =
    mediaId && !thumbnailFailed ? generateCandidateThumbnailUrl(mediaId, candidate.id) : null;
  // Feature-derived tag badges (kept honest: derived from CPS score & duration only)
  const displayTags = tags || [
    candidate.cps >= 90 ? "Trending Hook" : "Clear Value",
    candidate.duration_ms <= 40000 ? "High Retention" : "Deep Dive",
  ];

  // One hue family for the score: the brand violet, dimmed as the score
  // drops. Status colours (cyan/amber/red) stay reserved for job state.
  const scoreColor =
    candidate.cps >= 90
      ? "text-laqta-200 border-laqta-500/60 bg-laqta-600/20"
      : candidate.cps >= 80
        ? "text-laqta-300 border-laqta-700/60 bg-laqta-950/60"
        : "text-slate-300 border-slate-700/70 bg-slate-900/70";

  const rawText = snippetText || candidate.hook || candidate.title || `Clip #${rank} Hook`;
  const displayText = cleanDisplayText(rawText);
  const durationSec = Math.round(candidate.duration_ms / 1000);
  const rationale = pickMeaningfulRationale(candidate);

  // Deterministic placeholder hue per candidate — not a real video frame.
  const hue = (parseInt(candidate.id.replace(/\D/g, ""), 10) || rank * 47) % 360;

  return (
    <li
      onClick={() => onSelect(candidate)}
      className={`group relative rounded-2xl border transition-all duration-200 cursor-pointer ${
        isSelected
          ? "border-laqta-500/70 bg-obsidian-900/90 shadow-neon-purple ring-1 ring-laqta-500/40"
          : "border-slate-800/80 bg-obsidian-900/50 hover:bg-obsidian-900/80 hover:border-laqta-700/60"
      }`}
      data-testid={`clip-card-${candidate.id}`}
    >
      {/*
        The whole card is the selection target. It is a real button stretched
        behind the content, so the card is operable by mouse and keyboard
        without nesting one interactive element inside another. It stops the
        click from bubbling to the card container, which handles the same
        action for pointer events that land outside the button.
      */}
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onSelect(candidate);
        }}
        aria-pressed={isSelected}
        aria-label={`Select clip ${rank}: ${displayText}`}
        title={rationale ?? undefined}
        className="absolute inset-0 z-0 rounded-2xl cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 focus-visible:ring-offset-2 focus-visible:ring-offset-obsidian-950"
      />

      {/* Visual content — pointer events are disabled so the stretched button
          above receives the click; the play control opts back in. */}
      <div className="relative z-10 p-3 pointer-events-none select-none">
        <div className="flex items-start gap-3">
          {/* Rank */}
          <span
            className={`text-xs font-bold font-mono w-5 text-center pt-1 shrink-0 ${
              isSelected ? "text-laqta-200" : "text-slate-500"
            }`}
            aria-hidden="true"
          >
            {rank}
          </span>

          {/* Thumbnail: real extracted frame when available, honest gradient
              placeholder otherwise (frames arrive via a background job). */}
          <div
            className="h-14 w-14 rounded-xl shrink-0 border border-slate-700/60 flex items-center justify-center overflow-hidden relative"
            style={
              thumbnailUrl
                ? undefined
                : {
                    background: `linear-gradient(135deg, hsl(${hue} 45% 14%), hsl(${
                      (hue + 40) % 360
                    } 55% 22%))`,
                  }
            }
          >
            {thumbnailUrl ? (
              <img
                src={thumbnailUrl}
                alt={`Preview frame for clip #${rank}`}
                loading="lazy"
                onError={() => setThumbnailFailed(true)}
                className="h-full w-full object-cover"
                data-testid={`clip-thumbnail-${candidate.id}`}
              />
            ) : (
              <Film className="h-5 w-5 text-white/50" aria-hidden="true" />
            )}
          </div>

          {/* Body: Score, Title, Time Range, Tags */}
          <div className="flex-1 min-w-0">
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0 flex-1">
                <span
                  className={`shrink-0 text-xs font-bold font-mono flex items-center gap-1 ${scoreColor} border rounded-md px-1.5 py-0.5`}
                  title={`Clip Potential Score: ${Math.round(candidate.cps)}/100`}
                >
                  <Gauge className="h-2.5 w-2.5" aria-hidden="true" />
                  {Math.round(candidate.cps)}
                </span>
                <h4 className="text-xs font-semibold text-white group-hover:text-laqta-200 transition truncate leading-snug">
                  <BidiText text={displayText} />
                </h4>
              </div>

              {/* Preview play button */}
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onSelect(candidate);
                }}
                className="pointer-events-auto relative z-20 shrink-0 h-7 w-7 rounded-full border border-slate-700/80 bg-obsidian-950/80 text-slate-300 hover:text-white hover:border-laqta-500/60 flex items-center justify-center transition focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 cursor-pointer"
                title={`Preview clip #${rank}`}
                aria-label={`Preview clip ${displayText}`}
              >
                <Play className="h-3 w-3 ml-0.5 fill-current" aria-hidden="true" />
              </button>
            </div>

            {/* Time range: start - end (duration) */}
            <div className="mt-1 flex items-center gap-1 text-[11px] font-mono text-slate-400">
              <Clock className="h-3 w-3 text-slate-500" aria-hidden="true" />
              <span>
                {formatMsAsClock(candidate.start_ms)} - {formatMsAsClock(candidate.end_ms)}
              </span>
              <span className="text-slate-500">({durationSec}s)</span>
            </div>

            {/* Feature tags */}
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {displayTags.map((tag, idx) => {
                const isBrand = tag.includes("Hook") || tag.includes("Trending");
                const isCyan = tag.includes("Retention") || tag.includes("Fast");
                const isEmerald = tag.includes("Value") || tag.includes("Clear");

                const tagColorClass = isBrand
                  ? "bg-laqta-950/80 text-laqta-200 border-laqta-800/50"
                  : isCyan
                    ? "bg-cyan-950/80 text-neon-cyan border-cyan-800/50"
                    : isEmerald
                      ? "bg-emerald-950/80 text-neon-emerald border-emerald-800/50"
                      : "bg-amber-950/80 text-amber-300 border-amber-800/50";

                return (
                  <span
                    key={idx}
                    className={`text-[10px] font-medium px-2 py-0.5 rounded-full border ${tagColorClass}`}
                  >
                    {tag}
                  </span>
                );
              })}
            </div>
          </div>
        </div>

        {/* Score rationale from the explainable scoring engine + render state */}
        <div className="mt-2 pt-2 border-t border-slate-800/60 flex items-center justify-between gap-2 text-[10px]">
          <span className="text-slate-400 font-medium truncate flex-1 min-w-0 flex items-center gap-1">
            <Zap className="h-3 w-3 shrink-0 text-laqta-300" aria-hidden="true" />
            <span className="truncate">{rationale ?? "Deterministic CPS — no LLM involved"}</span>
          </span>
          {isRendered && (
            <span
              className="shrink-0 text-[9px] font-bold px-1.5 py-0.5 rounded bg-emerald-950/80 text-neon-emerald border border-emerald-800/50 flex items-center gap-1"
              title="Short already rendered and ready to download"
            >
              <Check className="h-2.5 w-2.5" aria-hidden="true" />
              <span>Exported</span>
            </span>
          )}
        </div>
      </div>
    </li>
  );
};

/**
 * Memoised: the studio re-renders on every 1.5 s job poll, and the clip list
 * can hold dozens of cards. Re-rendering them all is wasted work.
 */
export const ClipCardItem = memo(ClipCardItemComponent);

export default ClipCardItem;
