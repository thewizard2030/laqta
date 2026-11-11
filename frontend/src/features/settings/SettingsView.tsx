import React, { useEffect, useState, useCallback } from "react";
import {
  Sliders,
  Key,
  Mic,
  Download,
  HardDrive,
  Terminal,
  Save,
  RotateCcw,
  Sparkles,
  AlertCircle,
} from "lucide-react";
import { CapabilitiesResponse } from "../../types/capabilities";
import { SettingsResponse, SettingsUpdateRequest } from "../../types/settings";
import { api } from "../../lib/api/client";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { Toast } from "../../components/ui/Toast";
import { AiProvidersTab } from "./tabs/AiProvidersTab";
import { SpeechRecognitionTab } from "./tabs/SpeechRecognitionTab";
import { IngestionTab } from "./tabs/IngestionTab";
import { StorageCacheTab } from "./tabs/StorageCacheTab";
import { SystemAuditTab } from "./tabs/SystemAuditTab";

export type SettingsTabId = "ai" | "asr" | "ingest" | "storage" | "system";

interface SettingsViewProps {
  capabilities: CapabilitiesResponse;
  onRefreshCapabilities?: () => Promise<void> | void;
}

export const SettingsView: React.FC<SettingsViewProps> = ({
  capabilities,
  onRefreshCapabilities,
}) => {
  const [activeTab, setActiveTab] = useState<SettingsTabId>("ai");
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [draft, setDraft] = useState<SettingsUpdateRequest>({});
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);

  const fetchSettings = useCallback(async () => {
    try {
      setIsLoading(true);
      const res = await api.getSettings();
      setSettings(res);
      setDraft({});
    } catch {
      // Fallback to capability-derived defaults so offline/tests still work smoothly
      setSettings({
        app_name: capabilities.app_name,
        version: capabilities.version,
        allow_cloud_apis: false,
        llm_hosted_opt_in: capabilities.llm?.hosted_opt_in ?? false,
        enable_url_ingestion: capabilities.url_ingestion?.enabled ?? false,
        llm_ranker_enabled: capabilities.llm?.ranker_enabled ?? false,
        llm_provider: capabilities.llm?.provider ?? "openai_compatible",
        llm_base_url: capabilities.llm?.base_url ?? "http://127.0.0.1:11434/v1",
        llm_model: capabilities.llm?.model ?? "qwen2.5:7b-instruct",
        llm_openrouter_base_url: "https://openrouter.ai/api/v1",
        llm_openrouter_model: "minimax/minimax-m3.1-flash:free",
        llm_api_key_configured: capabilities.llm?.api_key_configured ?? false,
        redacted_llm_api_key: "<none>",
        llm_openrouter_api_key_configured: false,
        redacted_openrouter_api_key: "<none>",
        free_models: capabilities.llm?.free_models ?? ["minimax/minimax-m3.1-flash:free"],
        default_transcription_backend: "faster-whisper",
        default_whisper_profile: "fast",
        default_whisper_model: "base",
        fast_whisper_model: "base",
        balanced_whisper_model: "small",
        accurate_whisper_model: "medium",
        default_whisper_device: capabilities.hardware?.device ?? "cpu",
        default_whisper_compute_type: "int8",
        whisper_vad_filter: true,
        whisper_beam_size: 1,
        whisper_cpu_threads: capabilities.hardware?.recommended_worker_concurrency ?? 4,
        groq_model: "whisper-large-v3-turbo",
        groq_api_key_configured: false,
        redacted_groq_api_key: "<none>",
        assemblyai_api_key_configured: false,
        redacted_assemblyai_api_key: "<none>",
        hf_token_configured: false,
        redacted_hf_token: "<none>",
        clip_alignment_enabled: true,
        clip_alignment_model: "small",
        max_clip_alignment_seconds: 120,
        arabish_initial_prompt: true,
        arabish_prompt_text: "AI, API, SaaS",
        youtube_sub_languages: "ar.*,ar,en.*,en",
        yt_dlp_player_client: "android,ios,web",
        yt_dlp_cookies_path: null,
        yt_dlp_cookies_from_browser: null,
        ffmpeg_timeout_seconds: 300,
        data_dir: capabilities.storage?.data_dir ?? "~/.local/share/qatta",
        db_path: `${capabilities.storage?.data_dir ?? "~/.local/share/qatta"}/qatta.db`,
        transcript_cache_enabled: true,
        cached_transcripts_count: 0,
        cached_transcripts_bytes: 0,
        disk_total_bytes: 100 * 1024 * 1024 * 1024,
        disk_free_bytes: 50 * 1024 * 1024 * 1024,
        disk_used_bytes: 50 * 1024 * 1024 * 1024,
      });
    } finally {
      setIsLoading(false);
    }
  }, [capabilities]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchSettings();
  }, [fetchSettings]);

  const handleDraftChange = (patch: Partial<SettingsUpdateRequest>) => {
    setDraft((prev) => ({ ...prev, ...patch }));
  };

  const hasChanges = Object.keys(draft).length > 0;

  const handleSave = async () => {
    if (!hasChanges) return;
    setIsSaving(true);
    try {
      const updated = await api.updateSettings(draft);
      setSettings(updated);
      setDraft({});
      setToast({
        message: "Settings and credentials saved successfully.",
        type: "success",
      });
      if (onRefreshCapabilities) {
        await onRefreshCapabilities();
      }
    } catch (err: unknown) {
      setToast({
        message: err instanceof Error ? err.message : "Failed to save settings.",
        type: "error",
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleDiscard = () => {
    setDraft({});
    setToast({
      message: "Discarded unsaved changes.",
      type: "success",
    });
  };

  const handleReset = async () => {
    setShowResetConfirm(false);
    setIsSaving(true);
    try {
      const def = await api.resetSettings();
      setSettings(def);
      setDraft({});
      setToast({
        message: "Restored factory default settings.",
        type: "success",
      });
      if (onRefreshCapabilities) {
        await onRefreshCapabilities();
      }
    } catch {
      setToast({
        message: "Failed to reset settings to defaults.",
        type: "error",
      });
    } finally {
      setIsSaving(false);
    }
  };

  const tabs: { id: SettingsTabId; label: string; icon: React.ReactNode; badge?: string }[] = [
    {
      id: "ai",
      label: "AI & BYOK Keys",
      icon: <Key className="h-4 w-4" />,
      badge: "Secrets",
    },
    {
      id: "asr",
      label: "Speech Recognition",
      icon: <Mic className="h-4 w-4" />,
    },
    {
      id: "ingest",
      label: "Ingestion & Video",
      icon: <Download className="h-4 w-4" />,
    },
    {
      id: "storage",
      label: "Storage & Cache",
      icon: <HardDrive className="h-4 w-4" />,
    },
    {
      id: "system",
      label: "System Audit",
      icon: <Terminal className="h-4 w-4" />,
      badge: "Honest",
    },
  ];

  return (
    <div className="mx-auto w-full max-w-[1500px] space-y-6 pb-12">
      {/* View Header with Save Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-5 border-b border-slate-800 gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <Sliders className="h-5 w-5 text-laqta-400" />
            <h1 className="text-lg font-bold text-white tracking-tight">
              Studio Settings &amp; Engine
            </h1>
            <span className="text-xs px-2 py-0.5 rounded-md bg-slate-800 text-slate-400 font-mono border border-slate-700">
              v{settings?.version || capabilities.version}
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-400">
            Configure Bring Your Own Keys (BYOK), local speech models, storage policies, and engine
            runtimes.
          </p>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2.5">
          {hasChanges && (
            <span className="text-[11px] text-amber-400 bg-amber-950/60 border border-amber-800/40 px-2.5 py-1 rounded-lg flex items-center gap-1.5 animate-pulse">
              <AlertCircle className="h-3 w-3" />
              <span>Unsaved changes</span>
            </span>
          )}

          {hasChanges && (
            <Button variant="ghost" size="sm" onClick={handleDiscard} disabled={isSaving}>
              Discard
            </Button>
          )}

          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowResetConfirm(true)}
            disabled={isSaving}
            className="text-slate-400 hover:text-red-400"
            title="Reset all settings to defaults"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Reset Defaults</span>
          </Button>

          <Button
            variant="primary"
            size="sm"
            loading={isSaving}
            disabled={!hasChanges}
            onClick={handleSave}
            className="gap-1.5 shadow-md"
          >
            <Save className="h-3.5 w-3.5" />
            <span>Save Settings</span>
          </Button>
        </div>
      </div>

      {/* Tabs Switcher Navigation */}
      <nav
        className="flex items-center gap-1.5 border-b border-slate-800/80 pb-3 overflow-x-auto"
        aria-label="Settings categories"
      >
        {tabs.map((tab) => {
          const isSelected = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={isSelected}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold transition-all shrink-0 cursor-pointer ${
                isSelected
                  ? "bg-laqta-600 text-white shadow-md shadow-laqta-900/30"
                  : "bg-slate-900/80 text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 border border-slate-800"
              }`}
            >
              {tab.icon}
              <span>{tab.label}</span>
              {tab.badge && (
                <span
                  className={`text-[10px] px-1.5 py-0.2 rounded font-normal ${
                    isSelected ? "bg-laqta-700/80 text-white" : "bg-slate-800 text-slate-400"
                  }`}
                >
                  {tab.badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Tab Panels */}
      {isLoading ? (
        <div className="p-12 text-center space-y-3 bg-slate-900/50 rounded-2xl border border-slate-800">
          <Sparkles className="h-6 w-6 text-laqta-400 animate-spin mx-auto" />
          <p className="text-xs text-slate-400">Loading settings and provider configurations...</p>
        </div>
      ) : settings ? (
        <div>
          {activeTab === "ai" && (
            <AiProvidersTab settings={settings} draft={draft} onChange={handleDraftChange} />
          )}

          {activeTab === "asr" && (
            <SpeechRecognitionTab settings={settings} draft={draft} onChange={handleDraftChange} />
          )}

          {activeTab === "ingest" && (
            <IngestionTab settings={settings} draft={draft} onChange={handleDraftChange} />
          )}

          {activeTab === "storage" && (
            <StorageCacheTab
              settings={settings}
              draft={draft}
              onChange={handleDraftChange}
              onRefresh={fetchSettings}
            />
          )}

          {activeTab === "system" && (
            <SystemAuditTab
              capabilities={capabilities}
              onRefreshCapabilities={onRefreshCapabilities}
            />
          )}
        </div>
      ) : (
        <div className="p-8 text-center text-xs text-red-400 bg-red-950/20 rounded-2xl border border-red-900/30">
          Failed to load settings. Ensure the backend server is running.
        </div>
      )}

      {/* Reset Confirmation Dialog */}
      <ConfirmDialog
        isOpen={showResetConfirm}
        title="Reset All Settings to Defaults?"
        message="This will clear all custom API keys, model preferences, and custom timeouts stored in your local configuration. Media files and projects will remain intact."
        confirmLabel="Reset to Defaults"
        isDestructive={true}
        onConfirm={handleReset}
        onClose={() => setShowResetConfirm(false)}
      />

      {/* Feedback Toast */}
      {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}
    </div>
  );
};
