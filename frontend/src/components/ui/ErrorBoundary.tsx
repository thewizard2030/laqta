import React from "react";
import { AlertTriangle, RotateCw, Home } from "lucide-react";

interface ErrorBoundaryProps {
  children: React.ReactNode;
  /** Shown instead of the default panel (e.g. "The studio failed to render"). */
  title?: string;
  /** Optional callback so the app can log or report the failure. */
  onError?: (error: Error, info: React.ErrorInfo) => void;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/**
 * Catches a render error and shows a recoverable panel.
 *
 * Without this, a single bad render blanks the whole studio — the user
 * sees a black screen with no way back. The panel states what happened, keeps
 * the reason (the error message) visible, and offers the two ways out:
 * retry the render, or go back to the dashboard.
 *
 * A React error boundary has to be a class component — that is a React
 * requirement, not a style choice.
 */
export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    // The studio is local: log to the console, never to a remote service.
    console.error("Laqta render error:", error, info.componentStack);
    this.props.onError?.(error, info);
  }

  private handleRetry = (): void => {
    this.setState({ error: null });
  };

  private handleReload = (): void => {
    window.location.reload();
  };

  render(): React.ReactNode {
    const { error } = this.state;
    if (!error) {
      return this.props.children;
    }

    return (
      <div
        role="alert"
        className="mx-auto w-full max-w-2xl rounded-2xl border border-red-900/60 bg-red-950/25 p-6 sm:p-8"
        data-testid="error-boundary"
      >
        <div className="flex items-start gap-3">
          <span className="p-2.5 rounded-xl bg-red-900/40 text-red-300 shrink-0">
            <AlertTriangle className="h-5 w-5" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <h2 className="text-base font-bold text-white tracking-tight">
              {this.props.title ?? "Something went wrong while rendering"}
            </h2>
            <p className="mt-1 text-sm text-slate-300 leading-relaxed">
              The studio hit an unexpected error. Your project and media are untouched — nothing was
              deleted.
            </p>
            <pre
              className="mt-3 max-h-40 overflow-auto rounded-xl border border-red-900/40 bg-obsidian-950/80 p-3 text-[11px] font-mono text-red-200 whitespace-pre-wrap"
              data-testid="error-boundary-message"
            >
              {error.message || String(error)}
            </pre>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={this.handleRetry}
                className="inline-flex items-center gap-1.5 rounded-xl laqta-gradient-surface hover:brightness-110 px-3 py-2 text-xs font-semibold text-white shadow-laqta-glow transition-[filter] cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
              >
                <RotateCw className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Try again</span>
              </button>
              <button
                type="button"
                onClick={this.handleReload}
                className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-obsidian-950/70 px-3 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-800/70 transition cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
              >
                <Home className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Reload the studio</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }
}

export default ErrorBoundary;
