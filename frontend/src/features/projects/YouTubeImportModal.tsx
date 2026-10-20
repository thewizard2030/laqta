import React, { useState } from "react";
import { Youtube, ShieldCheck, Loader2, Lock } from "lucide-react";
import { Modal } from "../../components/ui/Modal";
import { api, ApiClientError } from "../../lib/api/client";

interface YouTubeImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
  /** Called after the backend accepted the gated import (202, job queued). */
  onQueued: (jobId: string) => void;
}

/**
 * Gated URL-import dialog (PRD FR-12).
 *
 * The backend itself is fail-closed (operator flag + rights confirmation +
 * public http(s) URL validation); this dialog only makes that contract
 * explicit to the user and can never bypass any of the gates server-side.
 */
export const YouTubeImportModal: React.FC<YouTubeImportModalProps> = ({
  isOpen,
  onClose,
  projectId,
  onQueued,
}) => {
  const [url, setUrl] = useState("");
  const [rightsConfirmed, setRightsConfirmed] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const trimmedUrl = url.trim();
  const isHttpUrl = /^https:\/\/\S+$/i.test(trimmedUrl) || /^http:\/\/\S+$/i.test(trimmedUrl);
  const canSubmit = isHttpUrl && rightsConfirmed && !isSubmitting;

  const resetAndClose = () => {
    setUrl("");
    setRightsConfirmed(false);
    setError(null);
    onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setIsSubmitting(true);
    setError(null);
    try {
      const result = await api.ingestMediaFromUrl(projectId, trimmedUrl, true);
      onQueued(result.job_id);
      resetAndClose();
    } catch (err) {
      const message =
        err instanceof ApiClientError
          ? err.message.replace(/^API request failed: \d+ /, "")
          : "Failed to start the import.";
      setError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={resetAndClose}
      title="Import from YouTube"
      description="Downloads one video with local yt-dlp onto this machine only."
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-1.5">
          <label htmlFor="youtube-url" className="text-xs font-semibold text-slate-300 block">
            Video URL
          </label>
          <input
            id="youtube-url"
            data-autofocus
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.youtube.com/watch?v=..."
            dir="ltr"
            className="w-full px-3 py-2 rounded-xl bg-obsidian-950/80 border border-slate-800 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-laqta-500/60 focus:ring-1 focus:ring-purple-500/40"
          />
        </div>

        {/* Rights confirmation — the backend refuses without this flag too. */}
        <label
          htmlFor="youtube-rights"
          className="flex items-start space-x-2.5 p-3 rounded-xl bg-obsidian-950/60 border border-slate-800/80 cursor-pointer select-none"
        >
          <input
            id="youtube-rights"
            type="checkbox"
            checked={rightsConfirmed}
            onChange={(e) => setRightsConfirmed(e.target.checked)}
            className="mt-0.5 h-4 w-4 accent-laqta-600"
          />
          <span className="text-[11px] text-slate-300 leading-relaxed">
            I confirm that I own this video or have permission to use it, in line with Laqta&apos;s
            rights policy.
          </span>
        </label>

        <div className="flex items-center space-x-2 px-3 py-2 rounded-xl bg-purple-950/40 border border-purple-800/40 text-laqta-200 text-[11px]">
          <Youtube className="h-3.5 w-3.5 text-red-400 shrink-0" aria-hidden="true" />
          <span>
            Video download + automatic transcript extraction (Arabic & English prioritized).
          </span>
        </div>

        <p className="flex items-start space-x-1.5 text-[10px] text-slate-500 leading-relaxed">
          <ShieldCheck
            className="h-3.5 w-3.5 text-neon-emerald shrink-0 mt-0.5"
            aria-hidden="true"
          />
          <span>
            The download runs locally in the background (no account, no cloud service) and every
            import requires the rights confirmation above. A local operator can still disable
            importing via QATTA_ENABLE_URL_INGESTION=false (PRD FR-12, reviewed 2026-10-19).
          </span>
        </p>

        {error && (
          <div
            role="alert"
            className="flex items-start space-x-2 p-2.5 rounded-xl bg-red-950/40 border border-red-800/60 text-red-300 text-[11px] leading-relaxed"
          >
            <Lock className="h-3.5 w-3.5 shrink-0 mt-0.5" aria-hidden="true" />
            <span>{error}</span>
          </div>
        )}

        <div className="flex items-center justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={resetAndClose}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:text-white bg-slate-800/60 hover:bg-slate-700/60 border border-slate-700/60 transition cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!canSubmit}
            className="inline-flex items-center justify-center px-4 py-2 rounded-xl bg-gradient-to-r from-laqta-600 to-indigo-600 hover:from-laqta-500 hover:to-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-semibold shadow-lg shadow-laqta-600/25 transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
          >
            {isSubmitting ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
            ) : (
              <Youtube className="h-3.5 w-3.5 mr-1.5" aria-hidden="true" />
            )}
            Start Import
          </button>
        </div>
      </form>
    </Modal>
  );
};
