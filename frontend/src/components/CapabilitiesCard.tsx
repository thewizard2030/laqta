import React from "react";
import { CheckCircle2, AlertTriangle, Terminal, Cpu, HardDrive, FileText } from "lucide-react";
import { CapabilitiesResponse } from "../types/capabilities";

interface CapabilitiesCardProps {
  capabilities: CapabilitiesResponse;
}

export const CapabilitiesCard: React.FC<CapabilitiesCardProps> = ({ capabilities }) => {
  const { ffmpeg, ffprobe, asr, hardware, storage, llm } = capabilities;
  const isOpenRouter = llm.provider === "openrouter";
  const llmReady = isOpenRouter
    ? llm.api_key_configured && llm.hosted_opt_in
    : llm.openai_compatible;

  return (
    <div className="mx-auto w-full max-w-[1500px] bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-sm">
      <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-800">
        <div className="flex items-center space-x-2">
          <Terminal className="h-4 w-4 text-laqta-400" />
          <h2 className="text-sm font-semibold text-slate-200">
            System Runtime & Media Capabilities
          </h2>
        </div>
        <span className="text-xs text-slate-400">Honest Environment Audit</span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* FFmpeg Capability */}
        <div className="bg-slate-950/60 border border-slate-800/80 rounded-lg p-3.5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs font-semibold text-slate-300">FFmpeg</span>
              {ffmpeg.available ? (
                <span className="flex items-center space-x-1 text-[11px] font-medium text-emerald-400 bg-emerald-950/50 px-2 py-0.5 rounded border border-emerald-800/40">
                  <CheckCircle2 className="h-3 w-3" />
                  <span>Available</span>
                </span>
              ) : (
                <span className="flex items-center space-x-1 text-[11px] font-medium text-amber-400 bg-amber-950/50 px-2 py-0.5 rounded border border-amber-800/40">
                  <AlertTriangle className="h-3 w-3" />
                  <span>Missing</span>
                </span>
              )}
            </div>
            <p className="text-xs text-slate-400 truncate" title={ffmpeg.version || "Not detected"}>
              {ffmpeg.version
                ? ffmpeg.version.split("Copyright")[0].trim()
                : "Binary not found in PATH"}
            </p>
          </div>

          <div className="mt-3 pt-2 border-t border-slate-800/60 flex items-center justify-between text-[11px]">
            <span className="text-slate-500">libass (Subtitles):</span>
            <span className={ffmpeg.has_libass ? "text-emerald-400 font-medium" : "text-slate-400"}>
              {ffmpeg.has_libass ? "Enabled" : "Disabled"}
            </span>
          </div>
        </div>

        {/* FFprobe Capability */}
        <div className="bg-slate-950/60 border border-slate-800/80 rounded-lg p-3.5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs font-semibold text-slate-300">FFprobe</span>
              {ffprobe.available ? (
                <span className="flex items-center space-x-1 text-[11px] font-medium text-emerald-400 bg-emerald-950/50 px-2 py-0.5 rounded border border-emerald-800/40">
                  <CheckCircle2 className="h-3 w-3" />
                  <span>Available</span>
                </span>
              ) : (
                <span className="flex items-center space-x-1 text-[11px] font-medium text-amber-400 bg-amber-950/50 px-2 py-0.5 rounded border border-amber-800/40">
                  <AlertTriangle className="h-3 w-3" />
                  <span>Missing</span>
                </span>
              )}
            </div>
            <p
              className="text-xs text-slate-400 truncate"
              title={ffprobe.version || "Not detected"}
            >
              {ffprobe.version
                ? ffprobe.version.split("Copyright")[0].trim()
                : "Binary not found in PATH"}
            </p>
          </div>

          <div className="mt-3 pt-2 border-t border-slate-800/60 flex items-center justify-between text-[11px]">
            <span className="text-slate-500">Media Inspection:</span>
            <span className={ffprobe.available ? "text-emerald-400 font-medium" : "text-amber-400"}>
              {ffprobe.available ? "Ready" : "Disabled"}
            </span>
          </div>
        </div>

        {/* ASR Speech Engine */}
        <div className="bg-slate-950/60 border border-slate-800/80 rounded-lg p-3.5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs font-semibold text-slate-300">ASR Adapter</span>
              <span className="flex items-center space-x-1 text-[11px] font-medium text-slate-400 bg-slate-800/60 px-2 py-0.5 rounded border border-slate-700/60">
                <FileText className="h-3 w-3 text-slate-400" />
                <span>Gate B</span>
              </span>
            </div>
            <div className="space-y-1 text-xs">
              <div className="flex justify-between items-center">
                <span className="text-slate-400">faster-whisper:</span>
                <span className={asr.faster_whisper ? "text-emerald-400" : "text-slate-500"}>
                  {asr.faster_whisper ? "Installed" : "Not installed"}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-slate-400">whisperX:</span>
                <span className={asr.whisperx ? "text-emerald-400" : "text-slate-500"}>
                  {asr.whisperx ? "Installed" : "Optional"}
                </span>
              </div>
            </div>
          </div>

          <div className="mt-3 pt-2 border-t border-slate-800/60 text-[11px] text-slate-500">
            CPU-first lazy model loading
          </div>
        </div>

        {/* Hardware & Storage */}
        <div className="bg-slate-950/60 border border-slate-800/80 rounded-lg p-3.5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs font-semibold text-slate-300">Hardware & Storage</span>
              <span className="flex items-center space-x-1 text-[11px] font-medium text-indigo-400 bg-indigo-950/50 px-2 py-0.5 rounded border border-indigo-800/40">
                <Cpu className="h-3 w-3" />
                <span className="uppercase">{hardware.device}</span>
              </span>
            </div>
            <div className="space-y-1 text-xs">
              <div className="flex justify-between items-center">
                <span className="text-slate-400">Max Concurrent Jobs:</span>
                <span className="text-slate-200 font-mono">
                  {hardware.recommended_worker_concurrency}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-slate-400">Storage writable:</span>
                <span className={storage.writable ? "text-emerald-400" : "text-red-400"}>
                  {storage.writable ? "Yes" : "Check permissions"}
                </span>
              </div>
            </div>
          </div>

          <div
            className="mt-3 pt-2 border-t border-slate-800/60 flex items-center space-x-1.5 text-[11px] text-slate-500 truncate"
            title={storage.data_dir}
          >
            <HardDrive className="h-3 w-3 shrink-0" />
            <span className="truncate">{storage.data_dir}</span>
          </div>
        </div>

        {/* LLM Reranker (optional; may be hosted) */}
        <div className="bg-slate-950/60 border border-slate-800/80 rounded-lg p-3.5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs font-semibold text-slate-300">Clip Ranking</span>
              <span
                className={`flex items-center space-x-1 text-[11px] font-medium px-2 py-0.5 rounded border ${
                  llmReady
                    ? "text-emerald-400 bg-emerald-950/50 border-emerald-800/40"
                    : "text-amber-400 bg-amber-950/50 border-amber-800/40"
                }`}
              >
                {llmReady ? (
                  <CheckCircle2 className="h-3 w-3" />
                ) : (
                  <AlertTriangle className="h-3 w-3" />
                )}
                <span>{llmReady ? "LLM active" : "Baseline scoring"}</span>
              </span>
            </div>
            <div className="space-y-1 text-xs">
              <div className="flex justify-between items-center gap-2">
                <span className="text-slate-400">Provider:</span>
                <span className="text-slate-200 font-mono truncate">
                  {isOpenRouter ? "openrouter" : "openai_compatible"}
                </span>
              </div>
              <div className="flex justify-between items-center gap-2">
                <span className="text-slate-400">Model:</span>
                <span className="text-slate-200 font-mono truncate" title={llm.model ?? undefined}>
                  {llm.model ?? "—"}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-slate-400">API key configured:</span>
                <span className={llm.api_key_configured ? "text-emerald-400" : "text-slate-500"}>
                  {llm.api_key_configured ? "Yes" : "No"}
                </span>
              </div>
            </div>
          </div>

          <div className="mt-3 pt-2 border-t border-slate-800/60 text-[11px] text-slate-500 leading-relaxed">
            {llm.disclosure ? (
              <span className="text-amber-300/90">{llm.disclosure}</span>
            ) : isOpenRouter ? (
              "Hosted adapter: transcript text leaves this device when enabled."
            ) : (
              "Local adapter: transcript text never leaves this device."
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
