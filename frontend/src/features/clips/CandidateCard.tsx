import React, { useMemo, useState } from "react";
import { Scissors, Sparkles, AlertTriangle, Loader2, Save, Play, Eye, Info } from "lucide-react";
import { Candidate } from "../../types/candidates";
import { TranscriptSegment } from "../../types/transcription";
import { BidiText } from "../../lib/i18n/BidiText";
import { formatMsAsClock } from "../../lib/i18n/bidi";
import { validateBoundaryEdit, BoundaryBounds } from "../../lib/validation/boundaries";

export const REVIEW_NOTICE =
  "AI suggestion — review before publishing. Clip boundaries and explanations may be wrong.";

interface CandidateCardProps {
  candidate: Candidate;
  rank: number;
  segments: TranscriptSegment[];
  bounds: BoundaryBounds;
  mediaFileUrl: string | null;
  isSaving: boolean;
  onSave: (payload: { start_ms: number; end_ms: number }) => Promise<void>;
}

const statusVisual: Record<string, string> = {
  suggested: "text-emerald-400 bg-emerald-950/50 border-emerald-800/40",
  penalized: "text-amber-400 bg-amber-950/50 border-amber-800/40",
  rejected: "text-slate-400 bg-slate-800/60 border-slate-700/60",
};

/** Segments overlapped by the candidate's [start, end) span, evidence-aligned. */
function excerptsForCandidate(
  segments: TranscriptSegment[],
  startMs: number,
  endMs: number,
): TranscriptSegment[] {
  return segments.filter((seg) => seg.end * 1000 > startMs && seg.start * 1000 < endMs);
}

export const CandidateCard: React.FC<CandidateCardProps> = ({
  candidate,
  rank,
  segments,
  bounds,
  mediaFileUrl,
  isSaving,
  onSave,
}) => {
  const [startSec, setStartSec] = useState((candidate.start_ms / 1000).toFixed(1));
  const [endSec, setEndSec] = useState((candidate.end_ms / 1000).toFixed(1));
  const [editError, setEditError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [showBreakdown, setShowBreakdown] = useState(false);

  const excerpts = useMemo(
    () => excerptsForCandidate(segments, candidate.start_ms, candidate.end_ms),
    [segments, candidate.start_ms, candidate.end_ms],
  );
  const excerptText = excerpts.length > 0 ? excerpts.map((seg) => seg.text).join(" ") : null;

  const edited =
    Number(startSec) * 1000 !== candidate.start_ms || Number(endSec) * 1000 !== candidate.end_ms;

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaveError(null);
    const startMs = Math.round(Number(startSec) * 1000);
    const endMs = Math.round(Number(endSec) * 1000);
    const result = validateBoundaryEdit(startMs, endMs, bounds);
    if (!result.ok) {
      setEditError(result.message);
      return;
    }
    setEditError(null);
    try {
      await onSave({ start_ms: result.startMs, end_ms: result.endMs });
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Saving the edit failed.");
    }
  };

  const cpsColor =
    candidate.cps >= 60
      ? "bg-emerald-950/70 border-emerald-700/50 text-emerald-300"
      : candidate.cps >= 25
        ? "bg-amber-950/70 border-amber-700/50 text-amber-300"
        : "bg-slate-800/80 border-slate-700/60 text-slate-300";

  const unavailable = candidate.feature_scores.filter((f) => !f.available);
  const available = candidate.feature_scores.filter((f) => f.available);

  return (
    <article
      aria-label={`Candidate ${rank}: ${candidate.title ?? "Untitled clip"}`}
      className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 shadow-lg space-y-4"
      data-testid="candidate-card"
    >
      {/* Header: rank, CPS, review notice */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="text-xs font-mono text-slate-500">#{rank}</span>
          <span
            className={`inline-flex items-baseline px-3 py-1 rounded-full border text-sm font-bold font-mono ${cpsColor}`}
            aria-label={`Clip Potential Score ${candidate.cps.toFixed(0)} of 100`}
            title={candidate.cps_interpretation}
          >
            CPS {candidate.cps.toFixed(0)}
          </span>
          <span
            className={`text-[11px] capitalize px-2.5 py-0.5 rounded-full border ${
              statusVisual[candidate.status] ?? statusVisual.rejected
            }`}
          >
            {candidate.status}
          </span>
          {candidate.boundary_edited && (
            <span className="text-[11px] text-indigo-300 bg-indigo-950/60 border border-indigo-800/40 px-2 py-0.5 rounded-full">
              Edited — re-scored deterministically
            </span>
          )}
        </div>
        <span className="inline-flex items-center gap-1 text-[11px] text-amber-300 bg-amber-950/40 border border-amber-800/30 px-2.5 py-1 rounded-full">
          <Sparkles className="h-3 w-3" aria-hidden="true" />
          <span tabIndex={0} role="note" aria-label={REVIEW_NOTICE}>
            AI suggestion — review required
          </span>
        </span>
      </div>

      {/* Title / hook */}
      <div className="space-y-1">
        <h4 className="text-sm font-semibold text-white">{candidate.title ?? "Untitled clip"}</h4>
        {candidate.hook && (
          <BidiText text={candidate.hook} as="p" className="text-xs text-slate-400" />
        )}
      </div>

      {/* Time range */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs font-mono text-slate-300">
        <span className="inline-flex items-center gap-1.5">
          <Scissors className="h-3.5 w-3.5 text-indigo-400" aria-hidden="true" />
          <span>
            {formatMsAsClock(candidate.start_ms)} &rarr; {formatMsAsClock(candidate.end_ms)}
          </span>
        </span>
        <span className="text-slate-500">{(candidate.duration_ms / 1000).toFixed(1)} s</span>
        <span className="text-slate-600">
          start {candidate.start_ms} ms &middot; end {candidate.end_ms} ms
        </span>
      </div>

      {/* Edit boundaries (user journey step 10) */}
      <form
        onSubmit={handleSave}
        noValidate
        className="bg-slate-950/70 border border-slate-800/80 rounded-xl p-3.5 space-y-2.5"
        aria-label={`Edit boundaries for candidate ${rank}`}
      >
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-medium text-slate-300">Edit cut points</span>
          {/* Loading while a save is in flight; never a fake success. */}
          {isSaving && (
            <span className="inline-flex items-center gap-1 text-[11px] text-cyan-400">
              <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
              Saving…
            </span>
          )}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label
              htmlFor={`start-input-${candidate.id}`}
              className="text-[11px] text-slate-400 block"
            >
              Start (seconds)
            </label>
            <input
              id={`start-input-${candidate.id}`}
              type="number"
              min={0}
              max={bounds.mediaDurationMs / 1000}
              step={0.1}
              value={startSec}
              onChange={(e) => setStartSec(e.target.value)}
              className="w-full bg-slate-900 border border-slate-800 text-white rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-600"
              aria-describedby={editError ? `edit-error-${candidate.id}` : undefined}
            />
          </div>
          <div className="space-y-1">
            <label
              htmlFor={`end-input-${candidate.id}`}
              className="text-[11px] text-slate-400 block"
            >
              End (seconds)
            </label>
            <input
              id={`end-input-${candidate.id}`}
              type="number"
              min={0}
              max={bounds.mediaDurationMs / 1000}
              step={0.1}
              value={endSec}
              onChange={(e) => setEndSec(e.target.value)}
              className="w-full bg-slate-900 border border-slate-800 text-white rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-600"
              aria-describedby={editError ? `edit-error-${candidate.id}` : undefined}
            />
          </div>
        </div>
        {editError && (
          <p
            id={`edit-error-${candidate.id}`}
            role="alert"
            className="text-[11px] text-red-400 flex items-center gap-1"
          >
            <AlertTriangle className="h-3 w-3" aria-hidden="true" />
            {editError}
          </p>
        )}
        {saveError && (
          <p role="alert" className="text-[11px] text-red-400 flex items-center gap-1">
            <AlertTriangle className="h-3 w-3" aria-hidden="true" />
            {saveError}
          </p>
        )}
        <button
          type="submit"
          disabled={isSaving || !edited}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-indigo-400 transition cursor-pointer"
        >
          <Save className="h-3.5 w-3.5" aria-hidden="true" />
          {isSaving ? "Saving…" : "Save boundaries"}
        </button>
      </form>

      {/* Transcript excerpt aligned to the candidate span */}
      <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-3.5 space-y-1.5">
        <div className="flex items-center gap-1.5 text-[11px] text-slate-400">
          <Eye className="h-3 w-3 text-indigo-400" aria-hidden="true" />
          <span>
            Transcript excerpt ({excerpts.length} segment
            {excerpts.length === 1 ? "" : "s"} in range)
          </span>
        </div>
        {excerptText ? (
          <BidiText text={excerptText} className="text-xs text-slate-200 leading-relaxed" />
        ) : (
          <p className="text-[11px] text-amber-400">
            Transcript excerpt unavailable for this span — word/segment evidence may not cover this
            time range.
          </p>
        )}
      </div>

      {/* Source time preview player (uses real local file when served) */}
      {mediaFileUrl && (
        <div className="space-y-2">
          <video
            controls
            preload="metadata"
            data-testid="candidate-video"
            className="w-full max-w-sm rounded-lg border border-slate-800 bg-black"
            src={mediaFileUrl + "#t=" + (candidate.start_ms / 1000).toFixed(3)}
            aria-label={`Source preview from ${formatMsAsClock(candidate.start_ms)} to ${formatMsAsClock(candidate.end_ms)}`}
          />
          <button
            type="button"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-slate-200 bg-slate-800 hover:bg-slate-700 border border-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-400 transition cursor-pointer"
            onClick={(e) => {
              const video = (e.currentTarget.closest("div") as HTMLDivElement).querySelector(
                "video",
              );
              if (video) {
                video.currentTime = candidate.start_ms / 1000;
                video.play().catch(() => {
                  /* autoplay may be blocked; controls remain available */
                });
              }
            }}
          >
            <Play className="h-3 w-3" aria-hidden="true" />
            Preview from start
          </button>
        </div>
      )}

      {/* Score breakdown */}
      <div>
        <button
          type="button"
          onClick={() => setShowBreakdown((v) => !v)}
          aria-expanded={showBreakdown}
          className="inline-flex items-center gap-1.5 text-xs text-slate-300 hover:text-white focus:outline-none focus:ring-2 focus:ring-indigo-400 rounded px-1 cursor-pointer"
        >
          <Info className="h-3.5 w-3.5 text-slate-500" aria-hidden="true" />
          {showBreakdown ? "Hide" : "Show"} score breakdown & explanation
        </button>
        {showBreakdown && (
          <div className="mt-2 space-y-2" data-testid="score-breakdown">
            {available.map((f) => (
              <div
                key={f.key}
                className="bg-slate-950/60 border border-slate-800/80 rounded-lg p-2.5"
              >
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-slate-200 font-medium">{f.label}</span>
                  <span className="font-mono text-slate-400">
                    {f.score === null ? "unavailable" : `${f.score.toFixed(0)}/100`}
                    {" · weight "}
                    {(f.effective_weight ?? f.nominal_weight).toFixed(2)}
                  </span>
                </div>
                <p className="text-[11px] text-slate-400 mt-1">{f.rationale}</p>
              </div>
            ))}
            {unavailable.length > 0 && (
              <div className="bg-slate-950/60 border border-amber-900/40 rounded-lg p-2.5">
                <p className="text-[11px] text-amber-300 font-medium">
                  Unavailable evidence ({unavailable.length}):
                </p>
                <ul className="mt-1 space-y-1">
                  {unavailable.map((f) => (
                    <li key={f.key} className="text-[11px] text-slate-400">
                      <span className="text-amber-200/80">{f.label}</span> — {f.rationale}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <ul className="space-y-1">
              {candidate.rationale.map((line, i) => (
                <li key={i} className="text-[11px] text-slate-400">
                  • {line}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </article>
  );
};
