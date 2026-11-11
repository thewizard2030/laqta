import React, { useState } from "react";
import { HardDrive, Database, Trash2, CheckCircle2, RefreshCw } from "lucide-react";
import {
  ClearCacheResponse,
  SettingsResponse,
  SettingsUpdateRequest,
} from "../../../types/settings";
import { Switch } from "../../../components/ui/Switch";
import { Button } from "../../../components/ui/Button";
import { ConfirmDialog } from "../../../components/ui/ConfirmDialog";
import { api } from "../../../lib/api/client";

interface StorageCacheTabProps {
  settings: SettingsResponse;
  draft: SettingsUpdateRequest;
  onChange: (patch: Partial<SettingsUpdateRequest>) => void;
  onRefresh: () => void;
}

export const StorageCacheTab: React.FC<StorageCacheTabProps> = ({
  settings,
  draft,
  onChange,
  onRefresh,
}) => {
  const [clearing, setClearing] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [clearResult, setClearResult] = useState<ClearCacheResponse | null>(null);

  const cacheEnabled = draft.transcript_cache_enabled ?? settings.transcript_cache_enabled;

  const totalGB = (settings.disk_total_bytes / 1024 ** 3).toFixed(1);
  const freeGB = (settings.disk_free_bytes / 1024 ** 3).toFixed(1);
  const usedGB = (settings.disk_used_bytes / 1024 ** 3).toFixed(1);
  const usedPercent =
    settings.disk_total_bytes > 0
      ? Math.round((settings.disk_used_bytes / settings.disk_total_bytes) * 100)
      : 0;

  const cacheMB = (settings.cached_transcripts_bytes / (1024 * 1024)).toFixed(2);

  const handleClearCache = async () => {
    setClearing(true);
    setShowConfirm(false);
    try {
      const res = await api.clearTranscriptCache();
      setClearResult(res);
      onRefresh();
    } catch {
      setClearResult({
        cleared_files: 0,
        freed_bytes: 0,
        message: "Failed to clear transcript cache.",
      });
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-200">
      {/* 1. Storage & Volume Health */}
      <section className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-5">
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div className="flex items-center gap-2.5">
            <HardDrive className="h-5 w-5 text-indigo-400" />
            <div>
              <h2 className="text-sm font-semibold text-white">Disk Storage & Locations</h2>
              <p className="text-xs text-slate-400">
                Laqta stores projects, media, and SQLite databases in your controlled local
                directory.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onRefresh}
            className="text-xs text-slate-400 hover:text-white flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-800/60 border border-slate-700/60"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            <span>Refresh Stats</span>
          </button>
        </div>

        {/* Visual Disk Usage */}
        <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between text-xs">
            <span className="font-semibold text-slate-300">Volume Storage</span>
            <span className="font-mono text-slate-400">
              {usedGB} GB used of {totalGB} GB ({freeGB} GB available)
            </span>
          </div>

          <div className="w-full h-3 bg-slate-900 rounded-full overflow-hidden border border-slate-800">
            <div
              className={`h-full transition-all duration-500 rounded-full ${
                usedPercent > 90
                  ? "bg-red-500"
                  : usedPercent > 75
                    ? "bg-amber-400"
                    : "bg-linear-to-r from-laqta-500 to-indigo-500"
              }`}
              style={{ width: `${Math.min(100, Math.max(3, usedPercent))}%` }}
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 text-xs">
            <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-lg">
              <span className="text-slate-500 block text-[11px]">Data Directory:</span>
              <span
                className="font-mono text-slate-200 text-[11px] truncate block"
                title={settings.data_dir}
              >
                {settings.data_dir}
              </span>
            </div>
            <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-lg">
              <span className="text-slate-500 block text-[11px]">Database Path:</span>
              <span
                className="font-mono text-slate-200 text-[11px] truncate block"
                title={settings.db_path}
              >
                {settings.db_path}
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* 2. Transcript Cache Management */}
      <section className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-800 gap-4">
          <div className="flex items-center gap-2.5">
            <Database className="h-5 w-5 text-emerald-400" />
            <div>
              <h2 className="text-sm font-semibold text-white">
                Content-Addressed Transcript Cache
              </h2>
              <p className="text-xs text-slate-400">
                Transcripts are cached by audio fingerprint so re-running candidate generation is
                instant.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400">Cache Active:</span>
            <Switch
              checked={cacheEnabled}
              onChange={(next) => onChange({ transcript_cache_enabled: next })}
              label="Enable Transcript Cache"
              testId="toggle-transcript-cache"
            />
          </div>
        </div>

        <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-slate-200">
                Cached Audio Fingerprints:
              </span>
              <span className="font-mono text-sm text-emerald-400 font-bold">
                {settings.cached_transcripts_count} files
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Total cache disk usage:{" "}
              <span className="font-mono text-slate-200 font-medium">{cacheMB} MB</span>
            </p>
          </div>

          <Button
            variant="danger"
            size="sm"
            loading={clearing}
            disabled={settings.cached_transcripts_count === 0}
            onClick={() => setShowConfirm(true)}
            className="gap-1.5"
          >
            <Trash2 className="h-3.5 w-3.5" />
            <span>Clear Transcript Cache</span>
          </Button>
        </div>

        {clearResult && (
          <div
            className={`p-3 rounded-lg border text-xs flex items-center gap-2 ${
              clearResult.cleared_files > 0
                ? "bg-emerald-950/40 border-emerald-800/40 text-emerald-300"
                : "bg-slate-800/60 border-slate-700/60 text-slate-300"
            }`}
          >
            <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
            <span>{clearResult.message}</span>
          </div>
        )}
      </section>

      {/* Confirmation Modal */}
      <ConfirmDialog
        isOpen={showConfirm}
        title="Clear Transcript Cache?"
        message="Deleting the cache will remove pre-computed transcripts for previously processed files. They will be regenerated the next time you open them. Project data and media files are NOT affected."
        confirmLabel="Clear Cache"
        isDestructive={true}
        onConfirm={handleClearCache}
        onClose={() => setShowConfirm(false)}
      />
    </div>
  );
};
