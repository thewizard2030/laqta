import React, { useState } from "react";
import { AlertCircle, RefreshCw, Terminal, Copy, Check } from "lucide-react";

interface ErrorMessageProps {
  message: string;
  onRetry: () => void;
  isRetrying?: boolean;
  /** Short heading; can be overridden for non-connection errors. */
  title?: string;
}

const RETRY_COMMAND = "uvicorn app.main:app --host 127.0.0.1 --port 8000";

export const ErrorMessage: React.FC<ErrorMessageProps> = ({
  message,
  onRetry,
  isRetrying,
  title = "Backend Connection Offline",
}) => {
  const [isCopied, setIsCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(RETRY_COMMAND);
      setIsCopied(true);
      window.setTimeout(() => setIsCopied(false), 2000);
    } catch {
      // Clipboard may be unavailable; the command is still visible/readable.
    }
  };

  return (
    <div
      role="alert"
      aria-live="assertive"
      className="bg-red-950/30 border border-red-800/60 rounded-xl p-5 shadow-lg text-slate-200"
    >
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="flex items-start space-x-3.5">
          <div className="p-2 bg-red-900/40 border border-red-700/50 rounded-lg text-red-400 shrink-0 mt-0.5 sm:mt-0">
            <AlertCircle className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-red-300">{title}</h3>
            <p className="text-xs text-slate-300 mt-1 leading-relaxed">{message}</p>
            <div className="mt-2.5 flex items-center space-x-2 text-xs font-mono bg-slate-950/70 border border-slate-800 rounded px-2.5 py-1 text-slate-400 max-w-full">
              <Terminal className="h-3.5 w-3.5 text-slate-500 shrink-0" />
              <span className="truncate">{RETRY_COMMAND}</span>
              <button
                onClick={handleCopy}
                aria-label={isCopied ? "Command copied to clipboard" : "Copy command to clipboard"}
                className="ml-1 shrink-0 text-slate-500 hover:text-slate-200 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 rounded cursor-pointer"
              >
                {isCopied ? (
                  <Check className="h-3.5 w-3.5 text-emerald-400" />
                ) : (
                  <Copy className="h-3.5 w-3.5" />
                )}
              </button>
            </div>
          </div>
        </div>

        <button
          onClick={onRetry}
          disabled={isRetrying}
          className="inline-flex items-center space-x-2 px-4 py-2 rounded-lg bg-red-900/60 hover:bg-red-900 border border-red-700/60 text-white font-medium text-xs transition-colors shrink-0 disabled:opacity-50 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-red-400 self-end sm:self-center"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isRetrying ? "animate-spin" : ""}`} />
          <span>{isRetrying ? "Retrying..." : "Retry Connection"}</span>
        </button>
      </div>
    </div>
  );
};
