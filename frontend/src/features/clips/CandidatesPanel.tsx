import React, { useEffect, useState, useCallback } from "react";
import {
  Wand2,
  Loader2,
  AlertCircle,
  Sparkles,
  RefreshCw,
  Clock,
  XCircle,
  Scissors,
} from "lucide-react";
import { Candidate } from "../../types/candidates";
import { TranscriptResponse } from "../../types/transcription";
import { api, ApiClientError } from "../../lib/api/client";
import { generateMediaFileUrl } from "../../lib/api/mediaUrl";
import { DEFAULT_MIN_DURATION_MS, DEFAULT_MAX_DURATION_MS } from "../../lib/validation/boundaries";
import { CandidateCard, REVIEW_NOTICE } from "./CandidateCard";

export type LoadState = "idle" | "loading" | "ready" | "error";

export interface TranscriptionJobState {
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  errorMessage: string | null;
}

interface CandidatesPanelProps {
  mediaId: string;
  mediaDurationMs: number;
  transcripts: TranscriptResponse[];
  transcriptionJob: TranscriptionJobState | null;
  onRetryTranscription?: () => void;
}

const SCORING_NOTICE =
  "Clip Potential Score (CPS) is a heuristic editorial quality score (0–100), " +
  "not a probability of views or virality. Weights are configuration, pending " +
  "human-rating evaluation.";

/**
 * Candidate review panel (user journey steps 7-10, FR-04/FR-05, FR-14).
 *
 * State honesty:
 * - loading: real fetch in flight
 * - error: real failed fetch, retryable
 * - empty: no candidates persisted — with different, accurate reasons
 *   (no transcript / transcription failed / transcription cancelled / ready)
 * - every card is labelled as an AI suggestion requiring review; no mock
 *   clips or fake success states exist in this production path.
 */
export const CandidatesPanel: React.FC<CandidatesPanelProps> = ({
  mediaId,
  mediaDurationMs,
  transcripts,
  transcriptionJob,
  onRetryTranscription,
}) => {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [rankingMethod, setRankingMethod] = useState<string>("baseline");
  const [isGenerating, setIsGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [savingCandidateId, setSavingCandidateId] = useState<string | null>(null);

  const hasTranscript = transcripts.length > 0;

  const fetchCandidates = useCallback(async () => {
    setLoadState("loading");
    setLoadError(null);
    try {
      const list = await api.listMediaCandidates(mediaId);
      setCandidates(list);
      setLoadState("ready");
    } catch (err) {
      setLoadError(
        err instanceof ApiClientError
          ? err.message
          : "Failed to load candidates from the local backend.",
      );
      setLoadState("error");
    }
  }, [mediaId]);

  useEffect(() => {
    fetchCandidates();
  }, [fetchCandidates]);

  const handleGenerate = async () => {
    setIsGenerating(true);
    setGenerateError(null);
    try {
      // The POST response IS the generation result (persisted, ranked data
      // straight from the backend — no client-side fabrication).
      const result = await api.generateCandidates(mediaId);
      setCandidates(result.candidates);
      setWarnings(result.warnings);
      setRankingMethod(result.ranking_method);
      setLoadState("ready");
    } catch (err) {
      try {
        const persisted = await api.listMediaCandidates(mediaId);
        if (persisted.length > 0) {
          setCandidates(persisted);
          setLoadState("ready");
          return;
        }
      } catch {
        // ignore fallback error
      }
      setGenerateError(
        err instanceof ApiClientError
          ? err.message
          : "Candidate generation failed on the local backend.",
      );
    } finally {
      setIsGenerating(false);
    }
  };

  const handleSave = async (candidateId: string, payload: { start_ms: number; end_ms: number }) => {
    setSavingCandidateId(candidateId);
    try {
      const updated = await api.updateCandidate(candidateId, payload);
      setCandidates((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
    } finally {
      setSavingCandidateId(null);
    }
  };

  const latestTranscript = transcripts[0] ?? null;

  const renderEmptyState = () => {
    if (transcriptionJob && transcriptionJob.status === "cancelled") {
      return (
        <div
          className="py-10 px-4 text-center border border-dashed border-slate-800 rounded-xl space-y-3"
          data-testid="candidates-cancelled"
        >
          <XCircle className="h-8 w-8 text-slate-500 mx-auto" aria-hidden="true" />
          <p className="text-xs font-medium text-slate-300">
            Transcription was cancelled — candidate generation is unavailable until transcription is
            rerun.
          </p>
          {onRetryTranscription && (
            <button
              type="button"
              onClick={onRetryTranscription}
              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 transition cursor-pointer"
            >
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Retry Transcription</span>
            </button>
          )}
        </div>
      );
    }
    if (transcriptionJob && transcriptionJob.status === "failed") {
      return (
        <div
          className="py-10 px-4 text-center border border-dashed border-slate-800 rounded-xl space-y-3"
          data-testid="candidates-transcription-failed"
        >
          <AlertCircle className="h-8 w-8 text-red-500 mx-auto" aria-hidden="true" />
          <p className="text-xs font-medium text-slate-300">
            Transcription failed
            {transcriptionJob.errorMessage ? `: ${transcriptionJob.errorMessage}` : ""}
          </p>
          <p className="text-[11px] text-slate-500">
            Fix the cause (check the job error in Processing Jobs) and retry transcription to enable
            candidates.
          </p>
          {onRetryTranscription && (
            <button
              type="button"
              onClick={onRetryTranscription}
              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 transition cursor-pointer"
            >
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Retry Transcription</span>
            </button>
          )}
        </div>
      );
    }
    if (transcriptionJob && transcriptionJob.status === "running") {
      return (
        <div
          className="py-10 px-4 text-center border border-dashed border-slate-800 rounded-xl space-y-3"
          data-testid="candidates-waiting-transcription"
        >
          <Clock className="h-8 w-8 text-amber-400 mx-auto" aria-hidden="true" />
          <p className="text-xs font-medium text-slate-300">
            Transcription is running. Candidates appear after the transcript is saved.
          </p>
        </div>
      );
    }
    if (!hasTranscript) {
      return (
        <div
          className="py-10 px-4 text-center border border-dashed border-slate-800 rounded-xl space-y-3"
          data-testid="candidates-no-transcript"
        >
          <Scissors className="h-8 w-8 text-slate-600 mx-auto" aria-hidden="true" />
          <p className="text-xs font-medium text-slate-300">No candidates yet</p>
          <p className="text-[11px] text-slate-500 max-w-md mx-auto">
            Candidates are generated from the transcript. Run transcription first, then generate
            candidates.
          </p>
        </div>
      );
    }
    return (
      <div
        className="py-10 px-4 text-center border border-dashed border-slate-800 rounded-xl space-y-3"
        data-testid="candidates-empty"
      >
        <Scissors className="h-8 w-8 text-slate-600 mx-auto" aria-hidden="true" />
        <p className="text-xs font-medium text-slate-300">No candidates yet</p>
        <p className="text-[11px] text-slate-500 max-w-md mx-auto">
          Generate transcript-aligned clip candidates locally. No clips exist until generation
          succeeds — nothing is faked in this view.
        </p>
        <button
          type="button"
          onClick={handleGenerate}
          disabled={isGenerating}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-indigo-400 transition cursor-pointer"
        >
          {isGenerating ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
          ) : (
            <Wand2 className="h-3.5 w-3.5" aria-hidden="true" />
          )}
          {isGenerating ? "Generating…" : "Generate candidates"}
        </button>
        {generateError && (
          <p role="alert" className="text-[11px] text-red-400">
            {generateError}
          </p>
        )}
      </div>
    );
  };

  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-5">
      {/* Section header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-800 gap-3">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-laqta-950/60 border border-laqta-800/40 rounded-xl text-laqta-400">
            <Scissors className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-white tracking-tight">Candidate Clips</h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Ranked by CPS — transcript-aligned suggestions, not final cuts.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1 text-[11px] text-amber-300 bg-amber-950/40 border border-amber-800/30 px-2.5 py-1 rounded-full">
            <Sparkles className="h-3 w-3" aria-hidden="true" />
            AI suggestion — review required
          </span>
          <button
            type="button"
            onClick={fetchCandidates}
            disabled={loadState === "loading"}
            className="p-1.5 text-slate-400 hover:text-white bg-slate-950 border border-slate-800 rounded-lg text-xs inline-flex items-center gap-1 focus:outline-none focus:ring-2 focus:ring-indigo-400 cursor-pointer"
            aria-label="Refresh candidates"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${loadState === "loading" ? "animate-spin" : ""}`}
              aria-hidden="true"
            />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Honest scoring notice */}
      <p className="text-[11px] text-slate-400" aria-label="Scoring notice">
        {SCORING_NOTICE}
      </p>

      {/* Loading state (real fetch) */}
      {loadState === "loading" && candidates.length === 0 && (
        <div
          className="py-10 text-center text-xs text-slate-500 flex items-center justify-center gap-2"
          data-testid="candidates-loading"
        >
          <Loader2 className="h-4 w-4 animate-spin text-indigo-400" aria-hidden="true" />
          <span>Loading candidates…</span>
        </div>
      )}

      {/* Failed fetch state (retryable) */}
      {loadState === "error" && (
        <div
          className="bg-red-950/30 border border-red-800/60 rounded-xl p-4 flex items-start justify-between gap-3"
          data-testid="candidates-error"
          role="alert"
        >
          <p className="text-xs text-red-300">{loadError}</p>
          <button
            type="button"
            onClick={fetchCandidates}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-red-900/60 hover:bg-red-900 border border-red-700/60 text-white text-xs focus:outline-none focus:ring-2 focus:ring-red-400 cursor-pointer"
          >
            <RefreshCw className="h-3 w-3" aria-hidden="true" />
            Retry
          </button>
        </div>
      )}

      {/* Empty / job-state reflections */}
      {loadState === "ready" && candidates.length === 0 && renderEmptyState()}

      {/* Ranked candidate cards */}
      {loadState === "ready" && candidates.length > 0 && (
        <div className="space-y-4" data-testid="candidates-list">
          {generateError && (
            <p role="alert" className="text-[11px] text-red-400">
              {generateError}
            </p>
          )}
          {(warnings.length > 0 || rankingMethod === "llm_reranked") && (
            <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-3 space-y-1">
              {rankingMethod === "llm_reranked" && (
                <p className="text-[11px] text-indigo-300 font-medium">
                  Ranking was refined by an optional LLM provider; CPS values remain the
                  deterministic baseline heuristic.
                </p>
              )}
              {warnings.map((w, i) => (
                <p key={i} className="text-[11px] text-slate-400">
                  {w}
                </p>
              ))}
            </div>
          )}
          {candidates.map((candidate, index) => (
            <CandidateCard
              key={candidate.id}
              candidate={candidate}
              rank={index + 1}
              segments={latestTranscript?.segments ?? []}
              bounds={{
                minDurationMs: DEFAULT_MIN_DURATION_MS,
                maxDurationMs: DEFAULT_MAX_DURATION_MS,
                mediaDurationMs,
              }}
              mediaFileUrl={generateMediaFileUrl(mediaId)}
              isSaving={savingCandidateId === candidate.id}
              onSave={(payload) => handleSave(candidate.id, payload)}
            />
          ))}
          <p className="text-[11px] text-slate-500">{REVIEW_NOTICE}</p>
        </div>
      )}
    </div>
  );
};
