import React from "react";
import { Download, Globe, ShieldAlert, Clock, Cookie } from "lucide-react";
import { SettingsResponse, SettingsUpdateRequest } from "../../../types/settings";
import { Switch } from "../../../components/ui/Switch";

interface IngestionTabProps {
  settings: SettingsResponse;
  draft: SettingsUpdateRequest;
  onChange: (patch: Partial<SettingsUpdateRequest>) => void;
}

export const IngestionTab: React.FC<IngestionTabProps> = ({ settings, draft, onChange }) => {
  const urlIngest = draft.enable_url_ingestion ?? settings.enable_url_ingestion;

  return (
    <div className="space-y-8 animate-in fade-in duration-200">
      {/* 1. URL Ingestion Policy & Gate */}
      <section className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-800 gap-4">
          <div className="flex items-center gap-2.5">
            <Download className="h-5 w-5 text-laqta-400" />
            <div>
              <h2 className="text-sm font-semibold text-white">URL Ingestion via yt-dlp (FR-12)</h2>
              <p className="text-xs text-slate-400">
                Extract captions and stream sections from authorized remote video links.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span
              className={`text-xs font-semibold px-2.5 py-1 rounded-full border ${
                urlIngest
                  ? "text-emerald-300 bg-emerald-950/60 border-emerald-800/40"
                  : "text-amber-400 bg-amber-950/50 border-amber-800/40"
              }`}
            >
              {urlIngest ? "Operator Enabled" : "Disabled (Fail-Closed)"}
            </span>
            <Switch
              checked={urlIngest}
              onChange={(next) => onChange({ enable_url_ingestion: next })}
              label="Enable URL Ingestion"
              testId="toggle-url-ingestion"
            />
          </div>
        </div>

        <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800 text-xs text-slate-400 space-y-2 leading-relaxed">
          <div className="flex items-center gap-2 text-amber-300 font-semibold">
            <ShieldAlert className="h-4 w-4" />
            <span>Rights & Responsibility Policy Notice</span>
          </div>
          <p>
            Per <strong className="text-white">docs/POLICY.md</strong>, URL downloading is
            fail-closed by default. When enabled, users remain strictly responsible for having the
            legal right to download or repurpose the imported material. Every remote import requires
            an interactive per-import rights confirmation modal.
          </p>
        </div>

        {/* Caption Languages & Player Strategy */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
              <Globe className="h-3.5 w-3.5 text-laqta-400" />
              <span>Preferred Subtitle Languages</span>
            </label>
            <input
              type="text"
              value={draft.youtube_sub_languages ?? settings.youtube_sub_languages}
              onChange={(e) => onChange({ youtube_sub_languages: e.target.value })}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white font-mono focus:border-indigo-500 focus:outline-none"
              placeholder="ar.*,ar,en.*,en"
            />
            <span className="text-[10px] text-slate-500 block">
              Comma-separated Regex/language tags. Avoid &apos;all&apos; to protect against platform
              rate limits.
            </span>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-300">Player Client Strategy</label>
            <input
              type="text"
              value={draft.yt_dlp_player_client ?? settings.yt_dlp_player_client}
              onChange={(e) => onChange({ yt_dlp_player_client: e.target.value })}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white font-mono focus:border-indigo-500 focus:outline-none"
              placeholder="android,ios,web"
            />
            <span className="text-[10px] text-slate-500 block">
              Order of client profiles tested to prevent HTTP 403 Forbidden on media downloads.
            </span>
          </div>
        </div>
      </section>

      {/* 2. Authentication & Cookie Extraction */}
      <section className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-5">
        <div className="flex items-center gap-2.5 pb-4 border-b border-slate-800">
          <Cookie className="h-5 w-5 text-amber-400" />
          <div>
            <h2 className="text-sm font-semibold text-white">Cookies & Restricted Media</h2>
            <p className="text-xs text-slate-400">
              Optional session authentication for age-restricted or member-only videos.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-300">
              Extract Cookies From Local Browser
            </label>
            <select
              value={
                draft.yt_dlp_cookies_from_browser ?? settings.yt_dlp_cookies_from_browser ?? ""
              }
              onChange={(e) => onChange({ yt_dlp_cookies_from_browser: e.target.value || null })}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:border-indigo-500 focus:outline-none"
            >
              <option value="">None (Anonymous download)</option>
              <option value="firefox">Firefox</option>
              <option value="chrome">Google Chrome</option>
              <option value="chromium">Chromium</option>
              <option value="brave">Brave</option>
              <option value="edge">Microsoft Edge</option>
            </select>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-300">
              Or Custom cookies.txt Path
            </label>
            <input
              type="text"
              value={draft.yt_dlp_cookies_path ?? settings.yt_dlp_cookies_path ?? ""}
              onChange={(e) => onChange({ yt_dlp_cookies_path: e.target.value || null })}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white font-mono focus:border-indigo-500 focus:outline-none"
              placeholder="/home/user/cookies.txt"
            />
          </div>
        </div>
      </section>

      {/* 3. Subprocess Deadlines */}
      <section className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-4">
        <div className="flex items-center gap-2.5 pb-4 border-b border-slate-800">
          <Clock className="h-5 w-5 text-indigo-400" />
          <div>
            <h2 className="text-sm font-semibold text-white">Subprocess Safety Deadlines</h2>
            <p className="text-xs text-slate-400">
              Prevents stuck rendering or probing commands from stalling background workers.
            </p>
          </div>
        </div>

        <div className="max-w-md space-y-1.5">
          <label className="text-xs font-semibold text-slate-300 flex justify-between">
            <span>FFmpeg Execution Timeout (seconds)</span>
            <span className="font-mono text-laqta-400">
              {draft.ffmpeg_timeout_seconds ?? settings.ffmpeg_timeout_seconds} s
            </span>
          </label>
          <input
            type="range"
            min={60}
            max={1800}
            step={30}
            value={draft.ffmpeg_timeout_seconds ?? settings.ffmpeg_timeout_seconds}
            onChange={(e) =>
              onChange({ ffmpeg_timeout_seconds: parseInt(e.target.value, 10) || 300 })
            }
            className="w-full accent-laqta-500 cursor-pointer"
          />
        </div>
      </section>
    </div>
  );
};
