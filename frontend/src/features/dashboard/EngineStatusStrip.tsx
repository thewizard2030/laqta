import React from "react";
import {
  Cpu,
  Film,
  HardDrive,
  Mic,
  Sparkles,
  Terminal,
  Youtube,
  Zap,
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
} from "lucide-react";
import { CapabilitiesResponse } from "../../types/capabilities";

type EngineState = "ready" | "missing" | "optional";

interface EngineItem {
  key: string;
  label: string;
  state: EngineState;
  value: string;
  hint?: string;
  icon: React.ReactNode;
}

interface EngineStatusStripProps {
  capabilities: CapabilitiesResponse | null;
}

const stateStyles: Record<
  EngineState,
  { dot: string; text: string; badge: string; badgeLabel: string }
> = {
  ready: {
    dot: "bg-neon-emerald",
    text: "text-neon-emerald",
    badge: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
    badgeLabel: "Ready",
  },
  missing: {
    dot: "bg-amber-400",
    text: "text-amber-300",
    badge: "border-amber-500/30 bg-amber-500/10 text-amber-300",
    badgeLabel: "Missing",
  },
  optional: {
    dot: "bg-slate-500",
    text: "text-slate-300",
    badge: "border-slate-700/60 bg-slate-800/60 text-slate-300",
    badgeLabel: "Optional",
  },
};

/**
 * Honest local-engine audit for the dashboard.
 *
 * Every tile mirrors a field of `GET /api/capabilities`. Optional components
 * (LLM endpoint, yt-dlp) are shown as optional/missing instead of being
 * presented as working features.
 */
export const EngineStatusStrip: React.FC<EngineStatusStripProps> = ({ capabilities }) => {
  if (!capabilities) {
    return (
      <section className="laqta-card rounded-2xl p-5" aria-label="Local engine status">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-300">
          <Terminal className="h-4 w-4 text-laqta-300" aria-hidden="true" />
          <span>Local engine status</span>
        </div>
        <p className="mt-2 text-xs text-slate-500">
          Capability probe has not returned yet — engine availability is unknown.
        </p>
      </section>
    );
  }

  const { ffmpeg, ffprobe, asr, llm, hardware, storage, url_ingestion } = capabilities;

  // The LLM adapter is optional and may be hosted. Report exactly what the
  // backend reports — never imply that a hosted model is a local one.
  const isOpenRouter = llm.provider === "openrouter";
  const llmReady = isOpenRouter
    ? llm.api_key_configured && llm.hosted_opt_in
    : llm.openai_compatible;
  const llmValue = isOpenRouter
    ? `OpenRouter · ${llm.model ?? "free model"}`
    : `local endpoint · ${llm.model ?? "any model"}`;
  const llmHint = isOpenRouter
    ? llm.api_key_configured
      ? "Hosted: transcript text leaves this device. The free models are zero-price but rate limited."
      : "OpenRouter selected but no API key is configured — the local heuristic scorer is used."
    : "An LLM endpoint is optional; ranking stays explainable and local without it";

  const items: EngineItem[] = [
    {
      key: "ffmpeg",
      label: "FFmpeg",
      state: ffmpeg.available ? "ready" : "missing",
      value: ffmpeg.available
        ? ffmpeg.version
          ? ffmpeg.version.split("Copyright")[0].trim()
          : "installed"
        : "not found in PATH",
      hint: ffmpeg.available
        ? ffmpeg.has_libass
          ? "libass subtitles enabled"
          : "libass missing — burned-in subtitles may fail"
        : "Required for rendering and thumbnail extraction",
      icon: <Film className="h-4 w-4" aria-hidden="true" />,
    },
    {
      key: "ffprobe",
      label: "FFprobe",
      state: ffprobe.available ? "ready" : "missing",
      value: ffprobe.available ? "media inspection ready" : "not found in PATH",
      hint: "Inspects duration, resolution and codecs of imported media",
      icon: <Terminal className="h-4 w-4" aria-hidden="true" />,
    },
    {
      key: "asr",
      label: "Speech engine",
      state: asr.faster_whisper ? "ready" : "missing",
      value: asr.faster_whisper ? "faster-whisper" : "no local ASR installed",
      hint: asr.faster_whisper
        ? asr.whisperx
          ? "faster-whisper + whisperX alignment available"
          : "faster-whisper only (whisperX optional)"
        : "Transcription is unavailable; clip scoring falls back to local heuristics",
      icon: <Mic className="h-4 w-4" aria-hidden="true" />,
    },
    {
      key: "ytdlp",
      label: "YouTube import",
      state: !url_ingestion.feature_flag
        ? "missing"
        : url_ingestion.yt_dlp.available
          ? "ready"
          : "missing",
      value: !url_ingestion.feature_flag
        ? "disabled by operator"
        : url_ingestion.yt_dlp.available
          ? "yt-dlp available"
          : "yt-dlp not installed",
      hint:
        url_ingestion.notice ||
        "URL imports stay gated behind the local flag, yt-dlp and a rights confirmation",
      icon: <Youtube className="h-4 w-4" aria-hidden="true" />,
    },
    {
      key: "llm",
      label: "Ranking assist",
      state: llmReady ? "ready" : "optional",
      value: llmReady ? llmValue : "local heuristic scoring only",
      hint: llmHint,
      icon: <Sparkles className="h-4 w-4" aria-hidden="true" />,
    },
    {
      key: "storage",
      label: "Storage",
      state: storage.writable ? "ready" : "missing",
      value: storage.writable ? "writable" : "read-only",
      hint: storage.data_dir,
      icon: <HardDrive className="h-4 w-4" aria-hidden="true" />,
    },
    {
      key: "device",
      label: "Device",
      state: "ready",
      value: hardware.cuda_available
        ? `${hardware.device.toUpperCase()} + CUDA`
        : hardware.device.toUpperCase(),
      hint: `Recommended worker concurrency: ${hardware.recommended_worker_concurrency}`,
      icon: <Cpu className="h-4 w-4" aria-hidden="true" />,
    },
  ];

  return (
    <section
      className="laqta-card rounded-2xl p-5"
      aria-label="Local engine status"
      data-testid="engine-status-strip"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
        <div className="flex items-center gap-2">
          <Zap className="h-4 w-4 text-neon-cyan" aria-hidden="true" />
          <h2 className="text-sm font-bold text-white tracking-tight">Local engine status</h2>
          <span className="text-[10px] font-mono uppercase tracking-wider rounded-full bg-obsidian-950/80 border border-slate-800 px-2 py-0.5 text-slate-400">
            {capabilities.local_only ? "local-only" : "remote enabled"}
          </span>
        </div>
        <p className="text-[11px] text-slate-500">
          Probed live from the local backend — nothing here is assumed.
        </p>
      </div>

      <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {items.map((item) => {
          const style = stateStyles[item.state];
          return (
            <li
              key={item.key}
              className="rounded-xl border border-slate-800/80 bg-obsidian-950/60 px-3.5 py-3 transition-colors duration-200 hover:border-laqta-500/40"
              data-testid={`engine-item-${item.key}`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                  <span className="text-slate-500">{item.icon}</span>
                  {item.label}
                </span>
                <span
                  className={`inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider ${style.badge}`}
                >
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${style.dot}`}
                    role="status"
                    aria-label={item.state}
                  />
                  {style.badgeLabel}
                </span>
              </div>
              <p className="mt-2 text-xs font-semibold text-slate-100 truncate" title={item.value}>
                {item.value}
              </p>
              {item.hint && (
                <p
                  className="mt-1 text-[10px] leading-relaxed text-slate-500 line-clamp-2"
                  title={item.hint}
                >
                  {item.hint}
                </p>
              )}
            </li>
          );
        })}
      </ul>

      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[10px] text-slate-500">
        <span className="inline-flex items-center gap-1">
          <CheckCircle2 className="h-3 w-3 text-neon-emerald" aria-hidden="true" />
          available
        </span>
        <span className="inline-flex items-center gap-1">
          <AlertTriangle className="h-3 w-3 text-amber-400" aria-hidden="true" />
          required component missing
        </span>
        <span className="inline-flex items-center gap-1">
          <CircleDashed className="h-3 w-3 text-slate-500" aria-hidden="true" />
          optional, local fallback used
        </span>
      </div>
    </section>
  );
};

export default EngineStatusStrip;
