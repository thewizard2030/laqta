import React from "react";
import { LaqtaMark } from "./LaqtaMark";
import { BRAND } from "../../lib/brand";
import { AlertCircle, RefreshCw, ShieldCheck } from "lucide-react";

interface SplashScreenProps {
  statusText?: string;
  isError?: boolean;
  errorMessage?: string;
  onRetry?: () => void;
  isRetrying?: boolean;
}

/**
 * Official Laqta Startup / Splash Screen.
 *
 * Provides a responsive, premium initial loading state showcasing the
 * official brand icon, wordmark, Arabic identity ("لقطة"), tagline,
 * and local-first verification badge.
 */
export const SplashScreen: React.FC<SplashScreenProps> = ({
  statusText = "Initializing local workbench…",
  isError = false,
  errorMessage = "",
  onRetry,
  isRetrying = false,
}) => {
  return (
    <div
      className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-obsidian-950 p-6 select-none animate-fadeIn"
      data-testid="laqta-splash-screen"
      role="status"
      aria-live="polite"
    >
      {/* Ambient background brand glows */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-24 left-1/2 -translate-x-1/2 w-96 h-96 rounded-full bg-laqta-600/15 blur-3xl"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -bottom-32 left-1/2 -translate-x-1/2 w-80 h-80 rounded-full bg-cyan-500/10 blur-3xl"
      />

      <div className="relative z-10 flex flex-col items-center text-center max-w-sm w-full">
        {/* Official Brand Mark with neon pulse glow */}
        <div className="relative mb-6">
          <div
            aria-hidden="true"
            className="absolute inset-0 rounded-2xl bg-laqta-600/30 blur-xl animate-pulse"
          />
          <div className="relative rounded-2xl p-1 bg-obsidian-900/80 border border-slate-700/50 shadow-2xl">
            <LaqtaMark size={76} title="Laqta logo" variant="badge" />
          </div>
        </div>

        {/* Wordmark and Bilingual Tag */}
        <div className="flex items-center gap-2 mb-2">
          <h1 className="text-3xl font-black tracking-tight text-white">{BRAND.name}</h1>
          <span
            dir="rtl"
            className="text-sm font-semibold px-2 py-0.5 rounded-md bg-purple-950/80 text-laqta-200 border border-purple-800/60 shadow-sm"
          >
            {BRAND.nameArabic}
          </span>
        </div>

        {/* Official Tagline */}
        <p className="text-xs font-medium tracking-wide text-slate-400 mb-6">
          Long Videos <span className="text-neon-cyan font-bold">to</span> Viral Shorts
        </p>

        {isError ? (
          /* Error State during startup */
          <div className="w-full space-y-4 animate-fadeUp">
            <div className="p-3.5 rounded-xl bg-red-950/40 border border-red-800/60 text-left flex items-start gap-3">
              <AlertCircle className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
              <div className="text-xs text-red-200 space-y-1">
                <p className="font-semibold text-white">Startup Error</p>
                <p className="text-red-300/90 leading-relaxed text-[11px]">{errorMessage}</p>
              </div>
            </div>

            {onRetry && (
              <button
                type="button"
                onClick={onRetry}
                disabled={isRetrying}
                className="w-full inline-flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl laqta-gradient-surface text-white text-xs font-semibold shadow-laqta-glow hover:brightness-110 active:scale-[0.98] transition disabled:opacity-50 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
              >
                <RefreshCw
                  className={`h-3.5 w-3.5 ${isRetrying ? "animate-spin" : ""}`}
                  aria-hidden="true"
                />
                <span>{isRetrying ? "Reconnecting…" : "Retry Connection"}</span>
              </button>
            )}
          </div>
        ) : (
          /* Normal Loading Progress */
          <div className="w-full space-y-3">
            <div className="h-1.5 w-full bg-obsidian-850 rounded-full overflow-hidden border border-slate-800/60 p-[1px]">
              <div className="h-full w-2/3 laqta-gradient-surface rounded-full animate-[sheen_1.6s_ease-in-out_infinite]" />
            </div>
            <p className="text-[11px] text-slate-400 font-medium">{statusText}</p>
          </div>
        )}

        {/* Local-first trust badge */}
        <div className="mt-8 flex items-center gap-1.5 text-[11px] text-slate-400">
          <ShieldCheck className="h-3.5 w-3.5 text-neon-emerald" aria-hidden="true" />
          <span>Local-first · 127.0.0.1 · 100% private</span>
        </div>
      </div>
    </div>
  );
};

export default SplashScreen;
