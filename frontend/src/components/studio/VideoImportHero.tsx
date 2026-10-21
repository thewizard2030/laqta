import React, { useState, useRef } from "react";
import { Upload, Film, Sparkles, CheckCircle2, AlertCircle, X } from "lucide-react";
import { YouTubeIcon } from "../ui/BrandIcons";
import { formatMsAsClock } from "../../lib/i18n/bidi";

interface VideoImportHeroProps {
  onUploadFile: (file: File) => Promise<void>;
  onYouTubeUrl?: (url: string) => Promise<void>;
  isUploading?: boolean;
  uploadProgress?: number;
  activeMedia?: {
    original_name: string;
    duration_ms: number;
    width: number;
    height: number;
    video_codec: string;
  } | null;
  onReplaceMedia?: () => void;
}

export const VideoImportHero: React.FC<VideoImportHeroProps> = ({
  onUploadFile,
  onYouTubeUrl,
  isUploading = false,
  uploadProgress = 0,
  activeMedia = null,
  onReplaceMedia,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isYoutubeModalOpen, setIsYoutubeModalOpen] = useState(false);
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [youtubeError, setYoutubeError] = useState("");

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      await onUploadFile(files[0]);
    }
  };

  const handleFileInputChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      await onUploadFile(files[0]);
    }
  };

  const handleYoutubeSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setYoutubeError("");

    if (!youtubeUrl.trim()) {
      setYoutubeError("Please enter a valid video link.");
      return;
    }

    if (!youtubeUrl.includes("youtube.com") && !youtubeUrl.includes("youtu.be")) {
      setYoutubeError("Please enter a valid YouTube video URL.");
      return;
    }

    if (onYouTubeUrl) {
      try {
        await onYouTubeUrl(youtubeUrl);
        setIsYoutubeModalOpen(false);
        setYoutubeUrl("");
      } catch (err) {
        setYoutubeError(err instanceof Error ? err.message : "Failed to process YouTube link.");
      }
    } else {
      setYoutubeError(
        "Direct YouTube download via yt-dlp is coming in the next release. Please upload a local video.",
      );
    }
  };

  return (
    <div
      className={`glass-card rounded-2xl p-5 border transition-all duration-300 relative overflow-hidden ${
        isDragging
          ? "border-laqta-500 shadow-neon-purple bg-laqta-950/30"
          : "border-slate-800/80 bg-obsidian-900/60"
      }`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      data-testid="video-import-hero"
    >
      {/* Background Neon Sheen */}
      <div className="absolute top-0 right-0 -mt-12 -mr-12 w-48 h-48 bg-linear-to-br from-purple-600/10 via-cyan-500/10 to-transparent rounded-full blur-2xl pointer-events-none" />

      {activeMedia ? (
        /* State 1: Active Media Loaded Summary */
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center space-x-3.5 min-w-0">
            <div className="h-12 w-12 rounded-xl bg-purple-950/60 border border-purple-500/30 flex items-center justify-center flex-shrink-0 text-neon-cyan shadow-sm">
              <Film className="h-6 w-6" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center space-x-2">
                <span className="font-semibold text-white truncate text-sm sm:text-base">
                  {activeMedia.original_name}
                </span>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-950/80 text-neon-emerald border border-emerald-800/50 flex items-center space-x-1">
                  <CheckCircle2 className="h-3 w-3" />
                  <span>Ready</span>
                </span>
              </div>
              <div className="flex items-center space-x-3 text-xs text-slate-400 mt-0.5">
                <span>{formatMsAsClock(activeMedia.duration_ms)}</span>
                <span>•</span>
                <span>
                  {activeMedia.width}×{activeMedia.height}
                </span>
                <span>•</span>
                <span className="uppercase font-mono text-[10px]">{activeMedia.video_codec}</span>
              </div>
            </div>
          </div>

          <div className="flex items-center space-x-2.5 flex-shrink-0">
            <button
              onClick={() => {
                if (onReplaceMedia) {
                  onReplaceMedia();
                } else {
                  fileInputRef.current?.click();
                }
              }}
              className="px-3.5 py-1.5 rounded-xl text-xs font-medium text-slate-300 hover:text-white bg-slate-800/60 hover:bg-slate-700/60 border border-slate-700/60 transition"
              data-testid="replace-media-btn"
            >
              Upload Different Video
            </button>
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileInputChange}
              accept="video/mp4,video/quicktime,video/x-matroska,video/webm"
              className="hidden"
            />
          </div>
        </div>
      ) : (
        /* State 2: Ready for Ingestion */
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-5">
          <div className="space-y-1">
            <div className="flex items-center space-x-2">
              <Sparkles className="h-4 w-4 text-laqta-200" />
              <h2 className="text-base sm:text-lg font-bold text-white tracking-tight">
                Import Your Video
              </h2>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-purple-900/40 text-laqta-200 border border-purple-700/40">
                100% Local Processing
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Upload long videos or podcasts to extract viral Shorts with AI hook detection and
              karaoke captions.
            </p>
          </div>

          {/* Action CTAs */}
          <div className="flex items-center space-x-3 flex-shrink-0">
            {/* Upload File CTA */}
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading}
              className="flex items-center space-x-2 px-4 py-2.5 rounded-xl text-xs sm:text-sm font-semibold text-white bg-linear-to-r from-purple-600 via-laqta-600 to-cyan-500 hover:from-purple-500 hover:to-cyan-400 shadow-neon-purple hover:shadow-neon-cyan transition-all active:scale-[0.98] disabled:opacity-50"
              data-testid="import-upload-btn"
            >
              <Upload className="h-4 w-4" />
              <span>{isUploading ? `Uploading ${uploadProgress}%...` : "Upload File"}</span>
            </button>
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileInputChange}
              accept="video/mp4,video/quicktime,video/x-matroska,video/webm"
              className="hidden"
              data-testid="hero-file-input"
            />

            {/* YouTube Link CTA */}
            <button
              onClick={() => setIsYoutubeModalOpen(true)}
              disabled={isUploading}
              className="flex items-center space-x-2 px-3.5 py-2.5 rounded-xl text-xs sm:text-sm font-medium text-slate-300 hover:text-white bg-obsidian-950/70 hover:bg-slate-800/80 border border-slate-700/60 hover:border-slate-600 transition disabled:opacity-50"
              data-testid="import-youtube-btn"
            >
              <YouTubeIcon className="h-4 w-4 text-red-400" />
              <span>YouTube Link</span>
            </button>
          </div>
        </div>
      )}

      {/* Upload Progress Bar (when active) */}
      {isUploading && (
        <div className="mt-4 pt-4 border-t border-slate-800/80 space-y-2">
          <div className="flex justify-between text-xs text-slate-300">
            <span>Importing and probing video with FFprobe...</span>
            <span className="font-mono text-neon-cyan">{uploadProgress}%</span>
          </div>
          <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
            <div
              className="h-full laqta-gradient-surface transition-all duration-200"
              style={{ width: `${uploadProgress}%` }}
            />
          </div>
        </div>
      )}

      {/* YouTube Modal Dialog */}
      {isYoutubeModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-obsidian-950/80 backdrop-blur-md">
          <div
            className="w-full max-w-md rounded-2xl glass-panel p-6 shadow-2xl border border-slate-800 space-y-4"
            data-testid="youtube-import-modal"
          >
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
              <div className="flex items-center space-x-2">
                <YouTubeIcon className="h-5 w-5 text-red-400" />
                <h3 className="text-sm font-bold text-white">Import from YouTube Link</h3>
              </div>
              <button
                onClick={() => setIsYoutubeModalOpen(false)}
                className="text-slate-400 hover:text-white p-1 rounded-lg"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form onSubmit={handleYoutubeSubmit} className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-300">Video URL</label>
                <input
                  type="url"
                  value={youtubeUrl}
                  onChange={(e) => setYoutubeUrl(e.target.value)}
                  placeholder="https://www.youtube.com/watch?v=..."
                  className="w-full px-3 py-2 rounded-xl bg-obsidian-950 border border-slate-700 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-400"
                  data-testid="youtube-url-input"
                />
              </div>

              {/* Honest Local-First Privacy Notice */}
              <div className="p-3 rounded-xl bg-slate-900/60 border border-slate-800 text-[11px] text-slate-400 space-y-1">
                <div className="flex items-center space-x-1.5 text-slate-300 font-medium">
                  <CheckCircle2 className="h-3.5 w-3.5 text-neon-emerald" />
                  <span>Local-First Download</span>
                </div>
                <p>
                  Downloaded directly onto your local device via local yt-dlp binary. Zero media
                  leaves your machine.
                </p>
              </div>

              {youtubeError && (
                <div className="flex items-center space-x-1.5 text-xs text-red-400 bg-red-950/40 p-2.5 rounded-xl border border-red-800/50">
                  <AlertCircle className="h-4 w-4 flex-shrink-0" />
                  <span>{youtubeError}</span>
                </div>
              )}

              <div className="flex justify-end space-x-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsYoutubeModalOpen(false)}
                  className="px-3 py-1.5 text-xs rounded-xl text-slate-400 hover:text-white hover:bg-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 text-xs font-semibold rounded-xl text-white laqta-gradient-surface hover:brightness-110 shadow-neon-purple"
                  data-testid="youtube-submit-btn"
                >
                  Fetch Video
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
