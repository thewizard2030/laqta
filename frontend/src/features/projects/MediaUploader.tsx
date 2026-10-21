import React, { useState, useRef } from "react";
import { UploadCloud, AlertCircle, Loader2, ShieldCheck } from "lucide-react";
import { MediaAsset } from "../../types/media";
import { api } from "../../lib/api/client";

interface MediaUploaderProps {
  projectId: string;
  onMediaUploaded: (media: MediaAsset) => void;
}

export const MediaUploader: React.FC<MediaUploaderProps> = ({ projectId, onMediaUploaded }) => {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isProbing, setIsProbing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      processFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      processFile(e.target.files[0]);
    }
  };

  const processFile = async (file: File) => {
    setErrorMessage(null);

    // Initial client-side extension check
    const extension = "." + file.name.split(".").pop()?.toLowerCase();
    const allowed = [".mp4", ".mov", ".mkv", ".webm"];
    if (!allowed.includes(extension)) {
      setErrorMessage(
        `Unsupported extension '${extension}'. Laqta accepts: ${allowed.join(", ")}.`,
      );
      return;
    }

    setIsUploading(true);
    setUploadProgress(0);
    setIsProbing(false);

    try {
      const media = await api.uploadMedia(projectId, file, (percent) => {
        setUploadProgress(percent);
        if (percent >= 100) {
          setIsProbing(true);
        }
      });
      onMediaUploaded(media);
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to upload and probe media.");
    } finally {
      setIsUploading(false);
      setIsProbing(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleDropzoneKeyDown = (e: React.KeyboardEvent) => {
    if (isUploading) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInputRef.current?.click();
    }
  };

  return (
    <div className="space-y-4">
      <div
        id="media-uploader-dropzone"
        role="button"
        tabIndex={isUploading ? -1 : 0}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => !isUploading && fileInputRef.current?.click()}
        onKeyDown={handleDropzoneKeyDown}
        aria-label="Drop your long-form video here, or press Enter to browse files"
        aria-disabled={isUploading || undefined}
        className={`relative border-2 border-dashed rounded-2xl p-8 sm:p-12 text-center transition-all cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 ${
          isDragging
            ? "border-laqta-500 bg-laqta-950/20"
            : "border-slate-800 hover:border-slate-700 bg-slate-900/40 hover:bg-slate-900/60"
        } ${isUploading ? "pointer-events-none opacity-80" : ""}`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".mp4,.mov,.mkv,.webm,video/mp4,video/quicktime,video/x-matroska,video/webm"
          className="hidden"
          onChange={handleFileChange}
          disabled={isUploading}
        />

        <div className="flex flex-col items-center justify-center space-y-4">
          <div className="h-16 w-16 rounded-2xl bg-slate-800/80 border border-slate-700 flex items-center justify-center text-laqta-400 shadow-xl">
            {isUploading ? (
              <Loader2 className="h-8 w-8 animate-spin text-laqta-400" />
            ) : (
              <UploadCloud className="h-8 w-8" />
            )}
          </div>

          {!isUploading ? (
            <>
              <div>
                <h4 className="text-base font-semibold text-white">
                  Drop your long-form video here, or{" "}
                  <span className="text-laqta-400 underline underline-offset-4">browse</span>
                </h4>
                <p className="text-xs text-slate-400 mt-1.5">
                  Supports MP4, MOV, MKV, and WebM containers
                </p>
              </div>

              <div className="flex items-center space-x-2 text-[11px] text-slate-400 bg-slate-950/60 border border-slate-800/80 px-3 py-1.5 rounded-full">
                <ShieldCheck className="h-3.5 w-3.5 text-indigo-400" />
                <span>Binary signature verification & safe local FFprobe stream inspection</span>
              </div>
            </>
          ) : (
            <div className="w-full max-w-md space-y-3" aria-live="polite">
              <div className="flex justify-between items-center text-xs">
                <span className="text-slate-300 font-medium">
                  {isProbing
                    ? "Validating & Probing with FFprobe..."
                    : "Importing video to local storage..."}
                </span>
                <span className="font-mono text-laqta-400">{uploadProgress}%</span>
              </div>

              <div
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={uploadProgress}
                aria-label="Upload progress"
                className="w-full bg-slate-800 rounded-full h-2 overflow-hidden"
              >
                <div
                  className="bg-linear-to-r from-laqta-500 to-indigo-500 h-2 rounded-full transition-all duration-150"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>

              {isProbing && (
                <p className="text-xs text-indigo-300 animate-pulse">
                  Inspecting video container, codecs, dimensions, and duration bounds...
                </p>
              )}
            </div>
          )}
        </div>
      </div>

      {errorMessage && (
        <div
          role="alert"
          className="bg-red-950/30 border border-red-800/60 rounded-xl p-4 text-xs text-red-300 flex items-start space-x-3 shadow-lg"
        >
          <AlertCircle className="h-4 w-4 shrink-0 text-red-400 mt-0.5" />
          <div className="space-y-1">
            <span className="font-semibold block">Media Import Rejected</span>
            <span className="text-slate-300 leading-relaxed block">{errorMessage}</span>
          </div>
        </div>
      )}
    </div>
  );
};
