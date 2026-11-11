import React from "react";
import { Mic, Languages, Layers } from "lucide-react";
import { SettingsResponse, SettingsUpdateRequest } from "../../../types/settings";
import { Switch } from "../../../components/ui/Switch";

interface SpeechRecognitionTabProps {
  settings: SettingsResponse;
  draft: SettingsUpdateRequest;
  onChange: (patch: Partial<SettingsUpdateRequest>) => void;
}

export const SpeechRecognitionTab: React.FC<SpeechRecognitionTabProps> = ({
  settings,
  draft,
  onChange,
}) => {
  const activeBackend =
    draft.default_transcription_backend ?? settings.default_transcription_backend;
  const currentProfile = draft.default_whisper_profile ?? settings.default_whisper_profile;
  const vadFilter = draft.whisper_vad_filter ?? settings.whisper_vad_filter;
  const clipAlignment = draft.clip_alignment_enabled ?? settings.clip_alignment_enabled;
  const arabishPrompt = draft.arabish_initial_prompt ?? settings.arabish_initial_prompt;

  return (
    <div className="space-y-8 animate-in fade-in duration-200">
      {/* 1. Default ASR Engine */}
      <section className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-5">
        <div className="flex items-center gap-2.5 pb-4 border-b border-slate-800">
          <Mic className="h-5 w-5 text-laqta-400" />
          <div>
            <h2 className="text-sm font-semibold text-white">Default Speech-to-Text Backend</h2>
            <p className="text-xs text-slate-400">
              Select which speech recognition engine transcribes your long-form videos by default.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {[
            {
              id: "faster-whisper",
              name: "Local faster-whisper",
              badge: "Local-First",
              desc: "Runs completely offline on your CPU or GPU using CTranslate2.",
            },
            {
              id: "groq_api",
              name: "Groq Cloud Whisper",
              badge: "Cloud (Fast)",
              desc: "Instant transcription via Groq LPU. Requires Groq API key.",
            },
            {
              id: "youtube_subs_first",
              name: "YouTube Captions-First",
              badge: "URL Pipeline",
              desc: "Extracts existing platform caption tracks without downloading full video.",
            },
          ].map((item) => {
            const isSelected = activeBackend === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onChange({ default_transcription_backend: item.id })}
                className={`p-3.5 rounded-xl border text-left transition-all ${
                  isSelected
                    ? "bg-laqta-950/40 border-laqta-500/60 ring-1 ring-laqta-500/40"
                    : "bg-slate-950/50 border-slate-800 hover:border-slate-700 hover:bg-slate-900/60"
                }`}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs font-semibold text-white">{item.name}</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                    {item.badge}
                  </span>
                </div>
                <p className="text-[11px] text-slate-400 leading-relaxed">{item.desc}</p>
              </button>
            );
          })}
        </div>
      </section>

      {/* 2. Local Whisper Profiles */}
      <section className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-5">
        <div className="flex items-center gap-2.5 pb-4 border-b border-slate-800">
          <Layers className="h-5 w-5 text-indigo-400" />
          <div>
            <h2 className="text-sm font-semibold text-white">Local Whisper Accuracy Profiles</h2>
            <p className="text-xs text-slate-400">
              Balanced two-pass transcription profiles optimized for 8 GB RAM and Arabic accuracy.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {[
            {
              id: "fast",
              label: "Fast",
              model: draft.fast_whisper_model ?? settings.fast_whisper_model,
              speed: "Fastest (3x on CPU)",
              ram: "~145 MB RAM",
              recommendation: "Best for quick triage of long material",
            },
            {
              id: "balanced",
              label: "Balanced",
              model: draft.balanced_whisper_model ?? settings.balanced_whisper_model,
              speed: "Moderate",
              ram: "~460 MB RAM",
              recommendation: "Recommended: high Arabic accuracy without thrashing",
            },
            {
              id: "accurate",
              label: "Accurate",
              model: draft.accurate_whisper_model ?? settings.accurate_whisper_model,
              speed: "Slow on CPU",
              ram: "~1.5 GB RAM",
              recommendation: "Highest fidelity for complex dialects",
            },
          ].map((profile) => {
            const isSelected = currentProfile === profile.id;
            return (
              <button
                key={profile.id}
                type="button"
                onClick={() => onChange({ default_whisper_profile: profile.id })}
                className={`p-4 rounded-xl border text-left transition-all relative ${
                  isSelected
                    ? "bg-indigo-950/40 border-indigo-500/60 ring-1 ring-indigo-500/40"
                    : "bg-slate-950/50 border-slate-800 hover:border-slate-700 hover:bg-slate-900/60"
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-bold text-white">{profile.label}</span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-indigo-300 border border-slate-700">
                    Model: {profile.model}
                  </span>
                </div>
                <div className="space-y-1 text-xs text-slate-400 mb-2">
                  <div className="flex justify-between">
                    <span>Speed:</span>
                    <span className="text-slate-200">{profile.speed}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Memory:</span>
                    <span className="text-slate-200">{profile.ram}</span>
                  </div>
                </div>
                <p className="text-[11px] text-slate-500 leading-tight pt-2 border-t border-slate-800/80">
                  {profile.recommendation}
                </p>
              </button>
            );
          })}
        </div>

        {/* Compute & Hardware Parameters */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-4 border-t border-slate-800/80">
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-300">Compute Device</label>
            <select
              value={draft.default_whisper_device ?? settings.default_whisper_device}
              onChange={(e) => onChange({ default_whisper_device: e.target.value })}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:border-indigo-500 focus:outline-none"
            >
              <option value="cpu">CPU (Default, highly compatible)</option>
              <option value="cuda">CUDA (NVIDIA GPU)</option>
            </select>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-300">Compute Type</label>
            <select
              value={draft.default_whisper_compute_type ?? settings.default_whisper_compute_type}
              onChange={(e) => onChange({ default_whisper_compute_type: e.target.value })}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:border-indigo-500 focus:outline-none"
            >
              <option value="int8">int8 (3x faster on CPU)</option>
              <option value="float16">float16 (Requires GPU)</option>
              <option value="int8_float16">int8_float16 (Mixed precision)</option>
            </select>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-300">Worker CPU Threads</label>
            <input
              type="number"
              min={1}
              max={16}
              value={draft.whisper_cpu_threads ?? settings.whisper_cpu_threads}
              onChange={(e) => onChange({ whisper_cpu_threads: parseInt(e.target.value, 10) || 4 })}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white font-mono focus:border-indigo-500 focus:outline-none"
            />
          </div>
        </div>
      </section>

      {/* 3. Audio Preprocessing & Arabic Dialect Handling */}
      <section className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-5">
        <div className="flex items-center gap-2.5 pb-4 border-b border-slate-800">
          <Languages className="h-5 w-5 text-emerald-400" />
          <div>
            <h2 className="text-sm font-semibold text-white">Arabic Speech & Audio Tuning</h2>
            <p className="text-xs text-slate-400">
              Dialect-aware prompt injection and Silero voice activity filtering.
            </p>
          </div>
        </div>

        {/* Silero VAD Filter */}
        <div className="flex items-center justify-between bg-slate-950/60 border border-slate-800/80 rounded-xl p-4">
          <div className="max-w-xl">
            <span className="text-xs font-semibold text-slate-200">
              Silero Voice Activity Detection (VAD)
            </span>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Filters silence, background ambient noise, and long pauses before feeding audio to
              Whisper. Prevents hallucinations during non-speech gaps.
            </p>
          </div>
          <Switch
            checked={vadFilter}
            onChange={(next) => onChange({ whisper_vad_filter: next })}
            label="Silero VAD Filter"
            testId="toggle-vad-filter"
          />
        </div>

        {/* Arablish Initial Prompt */}
        <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <span className="text-xs font-semibold text-slate-200">
                Arablish Technical Terms Prompting
              </span>
              <p className="text-[11px] text-slate-400 mt-0.5">
                Injects specialized vocabulary cues into Whisper so technical English terms (AI,
                API, SaaS) are rendered in clean Latin script rather than phonetic Arabic
                transliteration.
              </p>
            </div>
            <Switch
              checked={arabishPrompt}
              onChange={(next) => onChange({ arabish_initial_prompt: next })}
              label="Arablish Prompt Injection"
              testId="toggle-arabish-prompt"
            />
          </div>

          {arabishPrompt && (
            <div className="pt-2 border-t border-slate-800/60">
              <label className="text-[11px] text-slate-400 block mb-1">
                Injected Prompt Preview:
              </label>
              <textarea
                rows={2}
                value={draft.arabish_prompt_text ?? settings.arabish_prompt_text}
                onChange={(e) => onChange({ arabish_prompt_text: e.target.value })}
                className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2.5 text-xs text-slate-200 focus:border-indigo-500 focus:outline-none font-sans"
                dir="rtl"
              />
            </div>
          )}
        </div>

        {/* Pass 2 Clip Alignment */}
        <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <span className="text-xs font-semibold text-slate-200">
                Pass 2 Clip Alignment (Word-by-Word Timing)
              </span>
              <p className="text-[11px] text-slate-400 mt-0.5">
                Re-times words locally only on the winning 30-55s clips. Produces high-precision
                animated karaoke subtitles without requiring heavy full-video alignment.
              </p>
            </div>
            <Switch
              checked={clipAlignment}
              onChange={(next) => onChange({ clip_alignment_enabled: next })}
              label="Pass 2 Clip Alignment"
              testId="toggle-clip-alignment"
            />
          </div>

          {clipAlignment && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t border-slate-800/60">
              <div>
                <label className="text-[11px] text-slate-400 block mb-1">Alignment Model</label>
                <input
                  type="text"
                  value={draft.clip_alignment_model ?? settings.clip_alignment_model}
                  onChange={(e) => onChange({ clip_alignment_model: e.target.value })}
                  className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-white font-mono"
                  placeholder="small"
                />
              </div>
              <div>
                <label className="text-[11px] text-slate-400 block mb-1">
                  Max Alignment Seconds
                </label>
                <input
                  type="number"
                  value={draft.max_clip_alignment_seconds ?? settings.max_clip_alignment_seconds}
                  onChange={(e) =>
                    onChange({ max_clip_alignment_seconds: parseFloat(e.target.value) || 120.0 })
                  }
                  className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-white font-mono"
                />
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
};
