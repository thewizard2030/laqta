import React from "react";
import { Lock, HardDrive, EyeOff, Cloud } from "lucide-react";
import { LlmCapabilities } from "../types/capabilities";

interface PrivacyBannerProps {
  /** Optional LLM status; a HOSTED ranker changes what leaves the device. */
  llm?: LlmCapabilities | null;
}

export const PrivacyBanner: React.FC<PrivacyBannerProps> = ({ llm }) => {
  const hostedRankingActive =
    llm?.provider === "openrouter" && llm.api_key_configured && llm.hosted_opt_in;

  return (
    <div className="mx-auto w-full max-w-[1500px] bg-linear-to-r from-slate-900 via-laqta-950/30 to-slate-900 border border-laqta-900/40 rounded-2xl p-4 sm:p-5 shadow-lg">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="flex items-start space-x-3.5">
          <div className="p-2.5 bg-laqta-900/40 border border-laqta-700/50 rounded-lg text-laqta-300 shrink-0 mt-0.5 sm:mt-0">
            <Lock className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h3 className="text-sm font-semibold text-white">
                {hostedRankingActive
                  ? "Local Media, Hosted Ranking (Opt-In)"
                  : "100% Local Processing & Privacy Guarantee"}
              </h3>
              <span className="text-[10px] font-bold uppercase tracking-wider bg-laqta-500/20 text-laqta-200 border border-laqta-500/30 px-2 py-0.5 rounded">
                Local-First
              </span>
            </div>
            <p className="text-xs text-slate-300 mt-1 leading-relaxed max-w-3xl">
              Your video files, extracted audio, transcripts, and rendered clips never leave this
              machine. Laqta operates locally on{" "}
              <code className="text-cyan-300 font-mono">127.0.0.1</code> with zero cloud uploads, no
              mandatory accounts, and no background telemetry by default.
            </p>
            {hostedRankingActive && (
              <p className="flex items-start space-x-1.5 text-xs text-amber-200/90 mt-2 leading-relaxed max-w-3xl">
                <Cloud className="h-3.5 w-3.5 mt-0.5 shrink-0" aria-hidden="true" />
                <span>
                  Exception you opted into: the optional{" "}
                  <span className="font-mono">{llm?.provider}</span> ranker
                  {llm?.model ? (
                    <>
                      {" "}
                      (<span className="font-mono">{llm.model}</span>)
                    </>
                  ) : null}{" "}
                  sends the transcript text of the window being scored to a hosted service. Media
                  files, audio, renders and project data still never leave this machine.
                </span>
              </p>
            )}
          </div>
        </div>

        <div className="flex items-center space-x-4 text-xs text-slate-400 shrink-0 self-end sm:self-center border-t sm:border-t-0 border-slate-800 pt-2 sm:pt-0 w-full sm:w-auto justify-end">
          <div className="flex items-center space-x-1.5">
            <HardDrive className="h-3.5 w-3.5 text-slate-400" />
            <span>On-Device Storage</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <EyeOff className="h-3.5 w-3.5 text-slate-400" />
            <span>Zero Telemetry</span>
          </div>
        </div>
      </div>
    </div>
  );
};
