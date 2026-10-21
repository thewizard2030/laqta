import React, { useState } from "react";
import {
  FileText,
  Languages,
  Cpu,
  Clock,
  Sparkles,
  ChevronDown,
  ChevronUp,
  Loader2,
  CheckCircle2,
  Plus,
  Zap,
} from "lucide-react";
import { YouTubeIcon } from "../../components/ui/BrandIcons";
import { TranscriptResponse, TranscriptionRequest } from "../../types/transcription";

interface TranscriptViewerProps {
  mediaId: string;
  transcripts: TranscriptResponse[];
  isLoading: boolean;
  isTranscribing: boolean;
  isFasterWhisperAvailable?: boolean;
  onStartTranscription: (req: TranscriptionRequest) => Promise<void>;
  onRefreshTranscripts: () => Promise<void>;
}

export const TranscriptViewer: React.FC<TranscriptViewerProps> = ({
  transcripts,
  isLoading,
  isTranscribing,
  isFasterWhisperAvailable = false,
  onStartTranscription,
}) => {
  const [selectedTranscriptIndex, setSelectedTranscriptIndex] = useState(0);
  const [showConfigForm, setShowConfigForm] = useState(false);
  const [viewMode, setViewMode] = useState<"segments" | "fulltext">("segments");
  const [expandedSegmentId, setExpandedSegmentId] = useState<string | null>(null);

  // Form state
  const [profileMode, setProfileMode] = useState<"fast" | "balanced" | "accurate" | "custom">(
    "fast",
  );
  const [modelSize, setModelSize] = useState("base");
  const [language, setLanguage] = useState<string>("auto");
  const [wordTimestamps, setWordTimestamps] = useState(true);
  const [speedMode, setSpeedMode] = useState<"fast" | "accurate">("fast");
  const [durationLimit, setDurationLimit] = useState<"full" | "15min" | "30min">("full");
  const [provider, setProvider] = useState(isFasterWhisperAvailable ? "faster-whisper" : "fake");

  const currentTranscript: TranscriptResponse | undefined =
    transcripts.length > 0
      ? transcripts[Math.min(selectedTranscriptIndex, transcripts.length - 1)]
      : undefined;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (profileMode !== "custom") {
      // Performance profiles (docs/PERFORMANCE.md): the backend resolves
      // model/compute/beam/word-timing defaults; explicit language and
      // provider still win. Word timing for animated captions is re-derived
      // per selected clip at render time, so the full-video pass stays fast.
      await onStartTranscription({
        profile: profileMode,
        language: language === "auto" ? undefined : language,
        provider,
        max_duration_sec:
          durationLimit === "15min" ? 900 : durationLimit === "30min" ? 1800 : undefined,
      });
    } else {
      await onStartTranscription({
        model_size: modelSize,
        language: language === "auto" ? undefined : language,
        word_timestamps: wordTimestamps,
        provider,
        beam_size: speedMode === "fast" ? 1 : 5,
        max_duration_sec:
          durationLimit === "15min" ? 900 : durationLimit === "30min" ? 1800 : undefined,
      });
    }
    setShowConfigForm(false);
  };

  const formatSeconds = (sec: number): string => {
    const mins = Math.floor(sec / 60);
    const secs = (sec % 60).toFixed(1);
    return `${mins.toString().padStart(2, "0")}:${secs.padStart(4, "0")}`;
  };

  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-5">
      {/* Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-800 gap-3">
        <div className="flex items-center space-x-3">
          <div className="p-2.5 bg-indigo-950/60 border border-indigo-800/40 rounded-xl text-indigo-400">
            <FileText className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h3 className="text-sm font-semibold text-white tracking-tight">
                Speech Transcription
              </h3>
              {transcripts.length > 0 && (
                <span className="text-xs text-slate-500 font-mono">
                  ({transcripts.length} {transcripts.length === 1 ? "run" : "runs"} saved)
                </span>
              )}
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Local CPU speech-to-text using faster-whisper with int8 quantization.
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          {!showConfigForm && transcripts.length > 0 && (
            <button
              onClick={() => setShowConfigForm(true)}
              disabled={isTranscribing}
              className="inline-flex items-center space-x-1.5 px-3.5 py-1.5 rounded-xl text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition shadow-md shadow-indigo-950/40 cursor-pointer"
            >
              {isTranscribing ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span>Transcribing...</span>
                </>
              ) : (
                <>
                  <Plus className="h-3.5 w-3.5" />
                  <span>New Transcription Run</span>
                </>
              )}
            </button>
          )}
        </div>
      </div>

      {/* Transcription Job Submission Form */}
      {showConfigForm && (
        <form
          onSubmit={handleSubmit}
          className="bg-slate-950/80 border border-indigo-900/40 rounded-xl p-5 space-y-4"
        >
          <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
            <div className="flex items-center space-x-2">
              <Sparkles className="h-4 w-4 text-indigo-400" />
              <h4 className="text-xs font-semibold text-white">Configure Speech Recognition</h4>
            </div>
            <button
              type="button"
              onClick={() => setShowConfigForm(false)}
              className="text-xs text-slate-400 hover:text-white"
            >
              Cancel
            </button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Performance Profile */}
            <div className="space-y-1.5 sm:col-span-2">
              <label
                htmlFor="profile-select"
                className="text-xs font-medium text-slate-300 flex items-center space-x-1.5"
              >
                <Zap className="h-3.5 w-3.5 text-indigo-400" />
                <span>Performance Profile</span>
              </label>
              <select
                id="profile-select"
                value={profileMode}
                onChange={(e) => setProfileMode(e.target.value as typeof profileMode)}
                className="w-full bg-slate-900 border border-slate-800 text-white rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-indigo-500"
                data-testid="profile-select"
              >
                <option value="fast">
                  Fast — base model, int8, greedy beam 1, no full-video word alignment (recommended
                  on 8 GB)
                </option>
                <option value="balanced">
                  Balanced — small model, int8, greedy beam 1 (better Arabic, ~2× slower than Fast)
                </option>
                <option value="accurate">
                  Accurate — configurable high-accuracy model with full-video word alignment
                </option>
                <option value="custom">
                  Custom — manual model, beam and word-timestamp controls
                </option>
              </select>
              <p className="text-[11px] text-slate-500">
                Clip selection and per-clip word re-timing happen later, so animated captions still
                get precise words under Fast and Balanced without re-transcribing the whole video.
              </p>
              {profileMode === "accurate" && (
                <div className="p-2 rounded-lg bg-amber-950/40 border border-amber-800/40 text-[11px] text-amber-300">
                  Note: the Accurate profile transcribes the full video with word-level alignment
                  enabled; on CPU this typically takes several times longer than the other profiles.
                </div>
              )}
            </div>

            {profileMode === "custom" && (
              <>
                {/* Model Size */}
                <div className="space-y-1.5">
                  <label
                    htmlFor="model-size-select"
                    className="text-xs font-medium text-slate-300 flex items-center space-x-1.5"
                  >
                    <Cpu className="h-3.5 w-3.5 text-indigo-400" />
                    <span>Whisper Model Size</span>
                  </label>
                  <select
                    id="model-size-select"
                    value={modelSize}
                    onChange={(e) => setModelSize(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-800 text-white rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-indigo-500"
                  >
                    <option value="tiny">tiny (~75 MB, ~1 GB RAM, fastest)</option>
                    <option value="base">base (~145 MB, ~1.5 GB RAM, recommended default)</option>
                    <option value="small">small (~490 MB, ~2.5 GB RAM, balanced)</option>
                    <option value="medium">medium (~1.5 GB, ~5 GB RAM, high accuracy)</option>
                    <option value="large-v3">large-v3 (~3 GB, ~8 GB RAM, maximum quality)</option>
                  </select>
                  <p className="text-[11px] text-slate-500">
                    8 GB reference systems run comfortably on int8 &apos;base&apos; or
                    &apos;small&apos;.
                  </p>
                </div>

                {/* Language */}
                <div className="space-y-1.5">
                  <label
                    htmlFor="language-select"
                    className="text-xs font-medium text-slate-300 flex items-center space-x-1.5"
                  >
                    <Languages className="h-3.5 w-3.5 text-indigo-400" />
                    <span>Spoken Language</span>
                  </label>
                  <select
                    id="language-select"
                    value={language}
                    onChange={(e) => setLanguage(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-800 text-white rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-indigo-500"
                  >
                    <option value="auto">Auto-detect from audio</option>
                    <option value="ar">Arabic (العربية)</option>
                    <option value="en">English</option>
                    <option value="fr">French (Français)</option>
                    <option value="es">Spanish (Español)</option>
                    <option value="de">German (Deutsch)</option>
                  </select>
                  <p className="text-[11px] text-slate-500">
                    Specifying the language improves accuracy and decreases latency.
                  </p>
                </div>

                {/* Word Timestamps */}
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-slate-300 flex items-center space-x-1.5">
                    <Clock className="h-3.5 w-3.5 text-indigo-400" />
                    <span>Timestamp Granularity</span>
                  </label>
                  <label className="flex items-center space-x-2 text-xs text-slate-300 cursor-pointer pt-1">
                    <input
                      type="checkbox"
                      checked={wordTimestamps}
                      onChange={(e) => setWordTimestamps(e.target.checked)}
                      className="rounded border-slate-700 bg-slate-900 text-indigo-600 focus:ring-0"
                    />
                    <span>Request word-level timestamps when available</span>
                  </label>
                  <p className="text-[11px] text-slate-500">
                    Enables precise subtitle highlight and sentence boundary alignment.
                  </p>
                </div>

                {/* Speed & Decoding Mode */}
                <div className="space-y-1.5">
                  <label
                    htmlFor="speed-mode-select"
                    className="text-xs font-medium text-slate-300 flex items-center space-x-1.5"
                  >
                    <Zap className="h-3.5 w-3.5 text-cyan-400" />
                    <span>Decoding Speed Mode</span>
                  </label>
                  <select
                    id="speed-mode-select"
                    value={speedMode}
                    onChange={(e) => setSpeedMode(e.target.value as "fast" | "accurate")}
                    className="w-full bg-slate-900 border border-slate-800 text-white rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-indigo-500"
                  >
                    <option value="fast">
                      Fast (Greedy 1-Beam + Silero VAD) — ~3× faster, recommended on CPU
                    </option>
                    <option value="accurate">
                      High Precision (5-Beam Search) — standard quality, slower
                    </option>
                  </select>
                  <p className="text-[11px] text-slate-500">
                    Greedy decoding cuts CPU time by 60–70% with virtually identical accuracy on
                    clean dialogue.
                  </p>
                </div>
              </>
            )}

            {/* Audio Duration Scope */}
            <div className="space-y-1.5">
              <label
                htmlFor="duration-scope-select"
                className="text-xs font-medium text-slate-300 flex items-center space-x-1.5"
              >
                <Clock className="h-3.5 w-3.5 text-indigo-400" />
                <span>Audio Duration Scope</span>
              </label>
              <select
                id="duration-scope-select"
                value={durationLimit}
                onChange={(e) => setDurationLimit(e.target.value as "full" | "15min" | "30min")}
                className="w-full bg-slate-900 border border-slate-800 text-white rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-indigo-500"
              >
                <option value="full">Full Video Duration</option>
                <option value="15min">
                  First 15 Minutes (Rapid Shorts Draft — &lt;2 mins on CPU)
                </option>
                <option value="30min">First 30 Minutes (Balanced Draft)</option>
              </select>
              <p className="text-[11px] text-slate-500">
                For long videos (1–2+ hours), drafting the first 15 mins extracts initial Shorts
                immediately.
              </p>
            </div>

            {/* Provider */}
            <div className="space-y-1.5">
              <label
                htmlFor="provider-select"
                className="text-xs font-medium text-slate-300 flex items-center space-x-1.5"
              >
                <span>ASR Provider</span>
              </label>
              <select
                id="provider-select"
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
                className="w-full bg-slate-900 border border-slate-800 text-white rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-indigo-500"
              >
                <option value="faster-whisper">
                  faster-whisper (Local CPU){" "}
                  {isFasterWhisperAvailable ? "— Ready" : "— Not Installed"}
                </option>
                <option value="fake">
                  fake (Deterministic Test Fixture){" "}
                  {!isFasterWhisperAvailable ? "— Ready & Recommended" : ""}
                </option>
              </select>
              <p className="text-[11px] text-slate-500">
                Use &apos;fake&apos; to test UI and pipelines without loading model weights.
              </p>
              {!isFasterWhisperAvailable && provider === "faster-whisper" && (
                <div className="mt-2 p-2 rounded-lg bg-amber-950/40 border border-amber-800/40 text-[11px] text-amber-300">
                  Notice: faster-whisper is not detected in your backend Python environment. Select
                  &quot;fake&quot; to test the transcription workflow without downloading
                  dependencies, or run &apos;uv pip install faster-whisper&apos;.
                </div>
              )}
            </div>
          </div>

          <div className="flex items-center justify-end space-x-3 pt-3 border-t border-slate-800/80">
            <button
              type="button"
              onClick={() => setShowConfigForm(false)}
              className="px-3.5 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-white"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isTranscribing}
              className="inline-flex items-center space-x-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 transition cursor-pointer"
            >
              {isTranscribing && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              <span>Start Transcription</span>
            </button>
          </div>
        </form>
      )}

      {/* Loading state */}
      {isLoading && transcripts.length === 0 ? (
        <div className="py-8 text-center text-xs text-slate-500 flex items-center justify-center space-x-2">
          <Loader2 className="h-4 w-4 animate-spin text-indigo-400" />
          <span>Loading transcripts...</span>
        </div>
      ) : transcripts.length === 0 ? (
        /* Empty State */
        <div className="py-10 px-4 text-center border border-dashed border-slate-800 rounded-xl space-y-3">
          <FileText className="h-8 w-8 text-slate-600 mx-auto" />
          <div className="max-w-md mx-auto">
            <p className="text-xs font-medium text-slate-300">No transcripts yet</p>
            <p className="text-[11px] text-slate-500 mt-1">
              Transcribe this video locally using faster-whisper on CPU to produce timestamped
              segments and word-level timings without cloud dependencies.
            </p>
          </div>
          {!showConfigForm && (
            <button
              onClick={() => setShowConfigForm(true)}
              className="inline-flex items-center space-x-1.5 px-4 py-2 rounded-xl text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 transition shadow-md shadow-indigo-950/40 cursor-pointer"
            >
              <Plus className="h-3.5 w-3.5" />
              <span>Transcribe Video</span>
            </button>
          )}
        </div>
      ) : (
        /* Transcripts Display */
        currentTranscript && (
          <div className="space-y-4">
            {/* Top Toolbar: Run Selector and Granularity Badges */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-slate-950/60 border border-slate-800/80 rounded-xl p-3">
              {/* Historical Run Selector */}
              <div className="flex items-center space-x-2">
                <span className="text-xs text-slate-400 font-medium">Saved Run:</span>
                <select
                  value={selectedTranscriptIndex}
                  onChange={(e) => setSelectedTranscriptIndex(Number(e.target.value))}
                  className="bg-slate-900 border border-slate-800 text-white rounded-lg px-2.5 py-1 text-xs focus:outline-none focus:border-indigo-500"
                >
                  {transcripts.map((t, idx) => (
                    <option key={t.id} value={idx}>
                      #{transcripts.length - idx}: {t.model} ({t.language}) —{" "}
                      {new Date(t.created_at).toLocaleTimeString()}
                    </option>
                  ))}
                </select>
              </div>

              {/* Truthful Metadata & Granularity Badges */}
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center space-x-1 text-[11px] text-slate-300 bg-slate-900 border border-slate-800 px-2.5 py-0.5 rounded-full">
                  <Languages className="h-3 w-3 text-indigo-400" />
                  <span className="font-mono">{currentTranscript.language.toUpperCase()}</span>
                </span>

                <span className="inline-flex items-center space-x-1 text-[11px] text-slate-300 bg-slate-900 border border-slate-800 px-2.5 py-0.5 rounded-full">
                  <Cpu className="h-3 w-3 text-cyan-400" />
                  <span>{currentTranscript.model}</span>
                </span>

                {currentTranscript.provider === "youtube" && (
                  <span className="inline-flex items-center space-x-1 text-[11px] text-red-400 bg-red-950/60 border border-red-800/40 px-2.5 py-0.5 rounded-full font-medium">
                    <YouTubeIcon className="h-3 w-3 text-red-400" />
                    <span>YouTube Captions</span>
                  </span>
                )}

                {currentTranscript.timing_granularity === "word" ? (
                  <span className="inline-flex items-center space-x-1 text-[11px] text-emerald-400 bg-emerald-950/60 border border-emerald-800/40 px-2.5 py-0.5 rounded-full font-medium">
                    <CheckCircle2 className="h-3 w-3" />
                    <span>Word-level timings</span>
                  </span>
                ) : (
                  <span className="inline-flex items-center space-x-1 text-[11px] text-amber-400 bg-amber-950/60 border border-amber-800/40 px-2.5 py-0.5 rounded-full font-medium">
                    <Clock className="h-3 w-3" />
                    <span>Segment-level timings</span>
                  </span>
                )}
              </div>
            </div>

            {/* View Mode Toggle */}
            <div className="flex items-center justify-between border-b border-slate-800 pb-2">
              <div className="flex space-x-2">
                <button
                  onClick={() => setViewMode("segments")}
                  className={`px-3 py-1 text-xs font-medium rounded-lg transition-colors cursor-pointer ${
                    viewMode === "segments"
                      ? "bg-indigo-950/80 text-indigo-300 border border-indigo-800/50"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  Segments ({currentTranscript.segments.length})
                </button>
                <button
                  onClick={() => setViewMode("fulltext")}
                  className={`px-3 py-1 text-xs font-medium rounded-lg transition-colors cursor-pointer ${
                    viewMode === "fulltext"
                      ? "bg-indigo-950/80 text-indigo-300 border border-indigo-800/50"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  Full Text
                </button>
              </div>

              <span className="text-[11px] text-slate-500 font-mono">
                ID: {currentTranscript.id}
              </span>
            </div>

            {/* Content Display */}
            {viewMode === "fulltext" ? (
              <div
                dir={currentTranscript.language === "ar" ? "rtl" : "ltr"}
                className="bg-slate-950/70 border border-slate-800/80 rounded-xl p-4 text-xs text-slate-200 leading-relaxed max-h-96 overflow-y-auto whitespace-pre-wrap font-sans"
              >
                {currentTranscript.text}
              </div>
            ) : (
              <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
                {currentTranscript.segments.map((seg) => {
                  const isExpanded = expandedSegmentId === seg.id;
                  const hasWords = Boolean(seg.words && seg.words.length > 0);

                  return (
                    <div
                      key={seg.id}
                      className="bg-slate-950/60 border border-slate-800/80 hover:border-slate-700/80 rounded-xl p-3 space-y-2 transition-colors"
                    >
                      <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono">
                        <span className="text-indigo-400 font-medium">
                          {formatSeconds(seg.start)} &rarr; {formatSeconds(seg.end)}
                        </span>
                        <div className="flex items-center space-x-2">
                          <span className="text-slate-600">{seg.id}</span>
                          {hasWords && (
                            <button
                              onClick={() => setExpandedSegmentId(isExpanded ? null : seg.id)}
                              className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center space-x-0.5 cursor-pointer"
                              title="Toggle word timestamps"
                            >
                              <span>{seg.words?.length} words</span>
                              {isExpanded ? (
                                <ChevronUp className="h-3 w-3" />
                              ) : (
                                <ChevronDown className="h-3 w-3" />
                              )}
                            </button>
                          )}
                        </div>
                      </div>

                      <p
                        dir={currentTranscript.language === "ar" ? "rtl" : "ltr"}
                        className="text-xs text-slate-200 leading-normal"
                      >
                        {seg.text}
                      </p>

                      {/* Expanded Word Timestamps */}
                      {isExpanded && hasWords && (
                        <div className="mt-2 pt-2 border-t border-slate-800/80 flex flex-wrap gap-1.5">
                          {seg.words?.map((w, wIdx) => (
                            <span
                              key={wIdx}
                              className="inline-flex items-center space-x-1 text-[10px] bg-slate-900 border border-slate-800 px-2 py-0.5 rounded text-slate-300"
                              title={`Start: ${w.start.toFixed(2)}s, End: ${w.end.toFixed(2)}s${
                                w.probability ? `, Prob: ${(w.probability * 100).toFixed(0)}%` : ""
                              }`}
                            >
                              <span className="font-semibold text-white">{w.word}</span>
                              <span className="font-mono text-slate-500 text-[9px]">
                                {w.start.toFixed(1)}s
                              </span>
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )
      )}
    </div>
  );
};
