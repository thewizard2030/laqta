import React, { useState, useMemo } from "react";
import {
  Sparkles,
  ArrowUpDown,
  Wand2,
  Loader2,
  Cpu,
  Search,
  Zap,
  Scale,
  Target,
  ChevronDown,
} from "lucide-react";
import { Candidate } from "../../../types/candidates";
import { TranscriptSegment } from "../../../types/transcription";
import { cleanDisplayText } from "../../../lib/format";
import { ClipCardItem } from "./ClipCardItem";

interface SuggestedClipsListProps {
  candidates: Candidate[];
  selectedCandidateId: string | null;
  onSelectCandidate: (candidate: Candidate) => void;
  /** Real media asset id; enables real extracted preview frames on cards. */
  mediaId?: string | null;
  isAnalyzing?: boolean;
  onGenerateCandidates?: () => void;
  segments?: TranscriptSegment[];
  hasTranscript?: boolean;
  isTranscribing?: boolean;
  transcriptionProgress?: number;
  transcriptionStage?: string;
  onStartTranscription?: (profile: "fast" | "balanced" | "accurate", language?: string) => void;
  onSeekSegment?: (sec: number) => void;
  thumbnailEpoch?: number;
  renderedCandidateMap?: Map<string, string>;
}

/** How many cards are mounted at once. The rest are appended on demand. */
const CLIPS_PAGE_SIZE = 20;

export const SuggestedClipsList: React.FC<SuggestedClipsListProps> = ({
  candidates,
  selectedCandidateId,
  onSelectCandidate,
  mediaId = null,
  isAnalyzing = false,
  onGenerateCandidates,
  segments = [],
  hasTranscript = false,
  isTranscribing = false,
  transcriptionProgress = 0,
  transcriptionStage = "queued",
  onStartTranscription,
  onSeekSegment,
  thumbnailEpoch = 0,
  renderedCandidateMap,
}) => {
  const [activeTab, setActiveTab] = useState<"clips" | "transcript">("clips");
  const [sortBy, setSortBy] = useState<"score" | "time">("score");
  const [filterTag, setFilterTag] = useState<string>("all");
  const [transcriptSearch, setTranscriptSearch] = useState<string>("");
  const [selectedProfile, setSelectedProfile] = useState<"fast" | "balanced" | "accurate">("fast");
  const [selectedLanguage, setSelectedLanguage] = useState<string>("");
  const [visibleCount, setVisibleCount] = useState(CLIPS_PAGE_SIZE);

  const effectiveHasTranscript = hasTranscript || segments.length > 0;

  const sortedCandidates = useMemo(() => {
    const list = [...candidates];
    if (sortBy === "score") {
      list.sort((a, b) => b.cps - a.cps);
    } else {
      list.sort((a, b) => a.start_ms - b.start_ms);
    }

    if (filterTag === "all") return list;
    return list.filter((c) => {
      const isHook = c.cps >= 90;
      if (filterTag === "hook") return isHook;
      if (filterTag === "retention") return c.duration_ms <= 40000;
      return true;
    });
  }, [candidates, sortBy, filterTag]);

  // A new ranking or filter is a new list — start from the first page again.
  // Adjusted during render (React's documented pattern for a prop change)
  // instead of in an effect, which would show a stale page for one frame.
  const listKey = `${sortBy}:${filterTag}:${candidates.length}`;
  const [previousListKey, setPreviousListKey] = useState(listKey);
  if (previousListKey !== listKey) {
    setPreviousListKey(listKey);
    setVisibleCount(CLIPS_PAGE_SIZE);
  }

  const visibleCandidates = useMemo(
    () => sortedCandidates.slice(0, visibleCount),
    [sortedCandidates, visibleCount],
  );
  const remainingCandidates = sortedCandidates.length - visibleCandidates.length;

  // Filtered segments for transcript viewer tab
  const filteredSegments = useMemo(() => {
    if (!transcriptSearch.trim()) return segments;
    const q = transcriptSearch.toLowerCase();
    return segments.filter((s) => s.text.toLowerCase().includes(q));
  }, [segments, transcriptSearch]);

  const formatSeconds = (sec: number): string => {
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  // Map segments snippet for each candidate
  const getSnippetForCandidate = (c: Candidate): string => {
    let raw = c.hook || c.title || "";
    if (!raw) {
      const overlapped = segments.filter(
        (s) => s.end * 1000 > c.start_ms && s.start * 1000 < c.end_ms,
      );
      if (overlapped.length > 0) {
        raw =
          overlapped
            .map((s) => s.text)
            .join(" ")
            .slice(0, 90) + "...";
      } else {
        raw = `Candidate Clip (${Math.round(c.duration_ms / 1000)}s)`;
      }
    }
    return cleanDisplayText(raw);
  };

  const tabButtonClass = (isActive: boolean) =>
    `py-1.5 rounded-lg text-[11px] font-semibold transition cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 ${
      isActive ? "bg-laqta-900/70 text-white shadow-sm" : "text-slate-400 hover:text-white"
    }`;

  const filterPillClass = (isActive: boolean) =>
    `px-2.5 py-1 rounded-full border transition whitespace-nowrap focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 cursor-pointer ${
      isActive
        ? "bg-laqta-900/70 text-laqta-100 border-laqta-500/50"
        : "bg-obsidian-950/60 text-slate-400 border-slate-800 hover:text-slate-300"
    }`;

  return (
    <div
      className="flex flex-col h-full min-h-0 rounded-2xl border border-slate-800/80 bg-obsidian-900/60 backdrop-blur-md overflow-hidden"
      data-testid="suggested-clips-list"
    >
      {/* Header Bar */}
      <div className="shrink-0 px-4 pt-4 pb-3 border-b border-slate-800/80 space-y-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className="p-1.5 rounded-lg bg-laqta-950/70 border border-laqta-700/50 text-laqta-200 shrink-0">
            <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
          </span>
          <h3 className="text-sm font-bold text-white tracking-tight truncate">
            AI Suggested Clips
          </h3>
          <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-laqta-950/80 text-laqta-200 border border-laqta-800/50 shrink-0 ml-auto">
            {candidates.length} {candidates.length === 1 ? "clip" : "clips"}
          </span>
        </div>

        {/* Tab switch controls — full width so the labels never truncate */}
        {effectiveHasTranscript && (
          <div
            className="grid grid-cols-2 gap-1 bg-obsidian-950/70 p-1 rounded-xl border border-slate-800"
            role="tablist"
            aria-label="Suggested clips panel"
          >
            <button
              type="button"
              role="tab"
              id="clips-panel-tab"
              aria-controls="clips-panel"
              aria-selected={activeTab === "clips"}
              onClick={() => setActiveTab("clips")}
              className={tabButtonClass(activeTab === "clips")}
            >
              Clips
            </button>
            <button
              type="button"
              role="tab"
              id="transcript-panel-tab"
              aria-controls="transcript-panel"
              aria-selected={activeTab === "transcript"}
              onClick={() => setActiveTab("transcript")}
              className={tabButtonClass(activeTab === "transcript")}
            >
              Transcript
            </button>
          </div>
        )}

        {/* Clips-tab toolbar: sort control */}
        {activeTab === "clips" && (
          <div className="flex items-center justify-end">
            <button
              onClick={() => setSortBy((prev) => (prev === "score" ? "time" : "score"))}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-obsidian-950 text-slate-300 hover:text-white border border-slate-800 hover:border-laqta-700/60 transition shrink-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 cursor-pointer"
              title={
                sortBy === "score"
                  ? "Ranked by the explainable Clip Potential Score"
                  : "Ranked chronologically"
              }
              aria-label={sortBy === "score" ? "Sort by Clip Potential Score" : "Sort by Time"}
              data-testid="sort-toggle-btn"
            >
              <ArrowUpDown className="h-3 w-3 text-slate-400" aria-hidden="true" />
              <span className="text-[11px] whitespace-nowrap">
                Sort by: {sortBy === "score" ? "Clip Potential Score" : "Time"}
              </span>
            </button>
          </div>
        )}
      </div>

      {/* When on Transcript tab */}
      {effectiveHasTranscript && activeTab === "transcript" && (
        <div
          className="flex-1 flex flex-col min-h-0 space-y-3 p-4"
          role="tabpanel"
          id="transcript-panel"
          aria-labelledby="transcript-panel-tab"
        >
          <div className="relative shrink-0">
            <Search
              className="h-3.5 w-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500"
              aria-hidden="true"
            />
            <input
              type="text"
              value={transcriptSearch}
              onChange={(e) => setTranscriptSearch(e.target.value)}
              placeholder="Search transcript..."
              aria-label="Search transcript"
              className="w-full pl-8 pr-3 py-2 rounded-xl bg-obsidian-950 border border-slate-800 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-laqta-500/60"
            />
          </div>

          <div className="flex-1 overflow-y-auto space-y-2 pr-1 text-xs">
            {filteredSegments.length > 0 ? (
              filteredSegments.map((seg, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => onSeekSegment?.(seg.start)}
                  className="w-full text-left p-2.5 rounded-xl bg-obsidian-950/70 hover:bg-slate-800/80 border border-slate-800/60 transition cursor-pointer group focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
                >
                  <div className="flex items-center justify-between text-[10px] text-slate-500 font-mono mb-1">
                    <span className="text-neon-cyan group-hover:underline">
                      {formatSeconds(seg.start)} - {formatSeconds(seg.end)}
                    </span>
                    <span className="text-slate-500 text-[10px]">#{idx + 1}</span>
                  </div>

                  <p dir="auto" className="text-slate-200 leading-relaxed group-hover:text-white">
                    {seg.text}
                  </p>
                </button>
              ))
            ) : (
              <div className="p-4 text-center text-xs text-slate-400">
                No matching transcript segments.
              </div>
            )}
          </div>
        </div>
      )}

      {/* When on Clips tab */}
      {(!effectiveHasTranscript || activeTab === "clips") && (
        <div
          className="flex-1 flex flex-col min-h-0"
          role="tabpanel"
          id="clips-panel"
          aria-labelledby={effectiveHasTranscript ? "clips-panel-tab" : undefined}
        >
          {/* Filter Pills */}
          {candidates.length > 0 && (
            <div className="shrink-0 flex items-center gap-1.5 overflow-x-auto px-4 pt-3 pb-1 text-[11px]">
              <button
                onClick={() => setFilterTag("all")}
                aria-pressed={filterTag === "all"}
                className={filterPillClass(filterTag === "all")}
              >
                All Clips
              </button>
              <button
                onClick={() => setFilterTag("hook")}
                aria-pressed={filterTag === "hook"}
                className={filterPillClass(filterTag === "hook")}
              >
                Trending Hooks
              </button>
              <button
                onClick={() => setFilterTag("retention")}
                aria-pressed={filterTag === "retention"}
                className={filterPillClass(filterTag === "retention")}
              >
                High Retention
              </button>
            </div>
          )}

          {/* Candidate Cards List / Empty Workflow */}
          <div
            className="flex-1 overflow-y-auto space-y-2.5 p-4 pt-3"
            data-testid="clips-scroll-container"
          >
            {sortedCandidates.length > 0 ? (
              <>
                <ul className="space-y-2.5">
                  {visibleCandidates.map((candidate, idx) => (
                    <ClipCardItem
                      key={candidate.id}
                      rank={idx + 1}
                      candidate={candidate}
                      isSelected={selectedCandidateId === candidate.id}
                      onSelect={onSelectCandidate}
                      mediaId={mediaId}
                      snippetText={getSnippetForCandidate(candidate)}
                      thumbnailEpoch={thumbnailEpoch}
                      isRendered={renderedCandidateMap?.has(candidate.id) ?? false}
                    />
                  ))}
                </ul>

                {remainingCandidates > 0 && (
                  <button
                    type="button"
                    onClick={() => setVisibleCount((count) => count + CLIPS_PAGE_SIZE)}
                    className="w-full mt-1 flex items-center justify-center gap-1.5 rounded-xl border border-slate-800 bg-obsidian-950/70 py-2 text-[11px] font-semibold text-slate-300 hover:text-white hover:border-laqta-700/60 transition cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
                    data-testid="show-more-clips-btn"
                  >
                    <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
                    <span>
                      Show {Math.min(CLIPS_PAGE_SIZE, remainingCandidates)} more ·{" "}
                      {remainingCandidates} remaining
                    </span>
                  </button>
                )}
              </>
            ) : !effectiveHasTranscript && (onStartTranscription || isTranscribing) ? (
              /* Linear Guided Workflow: Transcribe Video First */
              <div className="flex flex-col items-center justify-center p-5 rounded-2xl bg-obsidian-950/70 border border-slate-800/80 space-y-4 text-center h-full">
                <div className="p-3 rounded-2xl bg-linear-to-br from-laqta-600/25 to-cyan-500/20 border border-laqta-700/50 text-neon-cyan">
                  <Cpu className="h-6 w-6" aria-hidden="true" />
                </div>

                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-neon-cyan">
                    Step 1 of 2
                  </p>
                  <h4 className="mt-1 text-sm font-bold text-white tracking-tight">
                    Transcribe Video Speech
                  </h4>
                  <p className="text-[11px] text-slate-400 mt-1.5 max-w-xs leading-relaxed">
                    Whisper AI will transcribe speech locally to generate karaoke captions and
                    discover viral hook moments.
                  </p>
                </div>

                {isTranscribing ? (
                  <div className="w-full p-4 rounded-xl bg-laqta-950/30 border border-laqta-800/50 space-y-2.5 text-left">
                    <div className="flex items-center justify-between text-xs text-neon-cyan font-medium">
                      <span className="flex items-center gap-1.5">
                        <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                        <span className="capitalize">Stage: {transcriptionStage}</span>
                      </span>
                      <span>{Math.round(transcriptionProgress)}%</span>
                    </div>
                    <div className="w-full bg-slate-900 rounded-full h-1.5 overflow-hidden">
                      <div
                        className="h-full laqta-gradient-surface transition-all duration-300"
                        style={{ width: `${Math.max(transcriptionProgress, 10)}%` }}
                      />
                    </div>
                    <span className="text-[10px] text-slate-400 block font-mono">
                      Transcribing offline on CPU (int8)...
                    </span>
                  </div>
                ) : (
                  <div className="w-full space-y-3 pt-1 text-left">
                    {/* Profile Selection */}
                    <div>
                      <label className="text-[11px] font-semibold text-slate-300 block mb-1.5">
                        Transcription Profile
                      </label>
                      <div className="grid grid-cols-3 gap-1.5 text-[11px]">
                        <button
                          type="button"
                          onClick={() => setSelectedProfile("fast")}
                          aria-pressed={selectedProfile === "fast"}
                          className={`p-2 rounded-lg border text-center transition cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 ${
                            selectedProfile === "fast"
                              ? "bg-laqta-900/70 text-white border-laqta-500/60 font-semibold"
                              : "bg-obsidian-950 text-slate-400 border-slate-800 hover:text-slate-200"
                          }`}
                        >
                          <Zap
                            className="h-3.5 w-3.5 mx-auto mb-0.5 text-laqta-200"
                            aria-hidden="true"
                          />
                          Fast
                          <span className="block text-[9px] text-slate-400 font-normal">Base</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => setSelectedProfile("balanced")}
                          aria-pressed={selectedProfile === "balanced"}
                          className={`p-2 rounded-lg border text-center transition cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 ${
                            selectedProfile === "balanced"
                              ? "bg-laqta-900/70 text-white border-laqta-500/60 font-semibold"
                              : "bg-obsidian-950 text-slate-400 border-slate-800 hover:text-slate-200"
                          }`}
                        >
                          <Scale
                            className="h-3.5 w-3.5 mx-auto mb-0.5 text-laqta-200"
                            aria-hidden="true"
                          />
                          Balanced
                          <span className="block text-[9px] text-slate-400 font-normal">Small</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => setSelectedProfile("accurate")}
                          aria-pressed={selectedProfile === "accurate"}
                          className={`p-2 rounded-lg border text-center transition cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 ${
                            selectedProfile === "accurate"
                              ? "bg-laqta-900/70 text-white border-laqta-500/60 font-semibold"
                              : "bg-obsidian-950 text-slate-400 border-slate-800 hover:text-slate-200"
                          }`}
                        >
                          <Target
                            className="h-3.5 w-3.5 mx-auto mb-0.5 text-laqta-200"
                            aria-hidden="true"
                          />
                          Accurate
                          <span className="block text-[9px] text-slate-400 font-normal">Large</span>
                        </button>
                      </div>
                    </div>

                    {/* Language selector */}
                    <div>
                      <label
                        htmlFor="suggested-clips-language"
                        className="text-[11px] font-semibold text-slate-300 block mb-1.5"
                      >
                        Language
                      </label>
                      <select
                        id="suggested-clips-language"
                        value={selectedLanguage}
                        onChange={(e) => setSelectedLanguage(e.target.value)}
                        className="w-full px-2.5 py-2 rounded-xl bg-obsidian-950 border border-slate-800 text-xs text-slate-300 focus:outline-none focus:border-laqta-500/60 cursor-pointer"
                      >
                        <option value="">Auto-Detect (Arabic / English / etc.)</option>
                        <option value="ar">Arabic (العربية)</option>
                        <option value="en">English</option>
                      </select>
                    </div>

                    {onStartTranscription && (
                      <button
                        type="button"
                        onClick={() =>
                          onStartTranscription(selectedProfile, selectedLanguage || undefined)
                        }
                        className="w-full py-2.5 px-3 rounded-xl text-xs font-semibold text-white laqta-gradient-surface hover:brightness-110 shadow-laqta-glow transition active:scale-95 cursor-pointer flex items-center justify-center gap-1.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
                      >
                        <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                        <span>Transcribe &amp; Discover Shorts</span>
                      </button>
                    )}
                  </div>
                )}
              </div>
            ) : candidates.length === 0 ? (
              /* Transcript is ready, but no candidates generated yet */
              <div className="h-full min-h-[240px] flex flex-col items-center justify-center text-center p-6 rounded-2xl bg-obsidian-950/40 border border-dashed border-slate-800 space-y-3">
                <div className="h-11 w-11 rounded-xl bg-laqta-950/60 border border-laqta-800/50 flex items-center justify-center text-laqta-200">
                  <Sparkles className="h-5 w-5" aria-hidden="true" />
                </div>
                <div>
                  <p className="text-xs font-semibold text-white">No AI clips generated yet</p>
                  <p className="text-[11px] text-slate-400 max-w-xs mt-1 leading-relaxed">
                    Analyze transcript to score viral hook potential and extract candidate shorts.
                  </p>
                </div>
                {onGenerateCandidates && (
                  <button
                    onClick={onGenerateCandidates}
                    disabled={isAnalyzing}
                    className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold text-white laqta-gradient-surface hover:brightness-110 shadow-laqta-glow transition active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
                    data-testid="generate-clips-btn"
                  >
                    {isAnalyzing ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                    ) : (
                      <Wand2 className="h-3.5 w-3.5" aria-hidden="true" />
                    )}
                    <span>{isAnalyzing ? "Analyzing..." : "Generate AI Clips"}</span>
                  </button>
                )}
              </div>
            ) : (
              <div className="p-4 text-center text-xs text-slate-400">
                No clips match the selected filter.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default SuggestedClipsList;
