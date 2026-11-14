import React, { useState } from "react";
import {
  Sparkles,
  Key,
  Eye,
  EyeOff,
  CheckCircle2,
  AlertTriangle,
  ExternalLink,
  ShieldAlert,
  Server,
  Cloud,
  Zap,
} from "lucide-react";
import {
  SettingsResponse,
  SettingsUpdateRequest,
  VerifyKeyResponse,
} from "../../../types/settings";
import { Switch } from "../../../components/ui/Switch";
import { Button } from "../../../components/ui/Button";
import { api } from "../../../lib/api/client";

interface AiProvidersTabProps {
  settings: SettingsResponse;
  draft: SettingsUpdateRequest;
  onChange: (patch: Partial<SettingsUpdateRequest>) => void;
}

export const AiProvidersTab: React.FC<AiProvidersTabProps> = ({ settings, draft, onChange }) => {
  // Local state for secret inputs
  const [showOpenRouterKey, setShowOpenRouterKey] = useState(false);
  const [showOpenAiKey, setShowOpenAiKey] = useState(false);
  const [showGroqKey, setShowGroqKey] = useState(false);
  const [showAssemblyAiKey, setShowAssemblyAiKey] = useState(false);
  const [showHfToken, setShowHfToken] = useState(false);

  // Verification state
  const [verifying, setVerifying] = useState<string | null>(null);
  const [verifyResult, setVerifyResult] = useState<Record<string, VerifyKeyResponse | null>>({});

  const allowCloud = draft.allow_cloud_apis ?? settings.allow_cloud_apis;
  const llmProvider = draft.llm_provider ?? settings.llm_provider;
  const rankerEnabled = draft.llm_ranker_enabled ?? settings.llm_ranker_enabled;
  const hostedOptIn = draft.llm_hosted_opt_in ?? settings.llm_hosted_opt_in;

  const handleTestKey = async (
    provider: string,
    candidateKey?: string,
    baseUrl?: string,
    model?: string,
  ) => {
    setVerifying(provider);
    setVerifyResult((prev) => ({ ...prev, [provider]: null }));
    try {
      const res = await api.verifyKey({
        provider,
        api_key: candidateKey || undefined,
        base_url: baseUrl,
        model,
      });
      setVerifyResult((prev) => ({ ...prev, [provider]: res }));
    } catch (err: unknown) {
      setVerifyResult((prev) => ({
        ...prev,
        [provider]: {
          ok: false,
          message: err instanceof Error ? err.message : "Connection failed",
          latency_ms: 0,
        },
      }));
    } finally {
      setVerifying(null);
    }
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-200">
      {/* 1. Master Cloud Policy Gate */}
      <div
        className={`rounded-2xl border p-5 transition-all ${
          allowCloud
            ? "bg-slate-900/90 border-laqta-500/40 shadow-lg shadow-laqta-950/40"
            : "bg-slate-950/60 border-slate-800"
        }`}
      >
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <div
              className={`p-2.5 rounded-xl border mt-0.5 ${
                allowCloud
                  ? "bg-laqta-500/10 border-laqta-500/30 text-laqta-400"
                  : "bg-slate-800/60 border-slate-700/60 text-slate-400"
              }`}
            >
              <Cloud className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-white">Master Cloud APIs Switch</h3>
                <span
                  className={`text-[11px] font-medium px-2 py-0.5 rounded-full border ${
                    allowCloud
                      ? "text-emerald-300 bg-emerald-950/60 border-emerald-800/40"
                      : "text-slate-400 bg-slate-900 border-slate-800"
                  }`}
                >
                  {allowCloud ? "Cloud Allowed" : "Local-Only Mode"}
                </span>
              </div>
              <p className="mt-1 text-xs text-slate-400 leading-relaxed max-w-2xl">
                Controls whether Laqta may send transcript text or audio to external cloud providers
                (OpenRouter, Groq, AssemblyAI). When off, all cloud endpoints are strictly
                fail-closed, preserving 100% offline isolation.
              </p>
            </div>
          </div>
          <div className="shrink-0 flex items-center gap-3">
            <Switch
              checked={allowCloud}
              onChange={(next) => onChange({ allow_cloud_apis: next })}
              label="Allow Cloud APIs"
              testId="toggle-allow-cloud-apis"
            />
          </div>
        </div>

        {allowCloud && (
          <div className="mt-4 pt-3 border-t border-slate-800/80 flex items-center gap-2 text-xs text-amber-300/90 bg-amber-950/20 px-3 py-2 rounded-lg border border-amber-900/30">
            <ShieldAlert className="h-4 w-4 shrink-0 text-amber-400" />
            <span>
              Transcript text and audio segments will leave this device when cloud providers are
              configured and selected.
            </span>
          </div>
        )}
      </div>

      {/* 2. LLM Reranking & BYOK Section */}
      <section className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-800 gap-3">
          <div className="flex items-center gap-2.5">
            <Sparkles className="h-5 w-5 text-indigo-400" />
            <div>
              <h2 className="text-sm font-semibold text-white">LLM Candidate Reranking</h2>
              <p className="text-xs text-slate-400">
                Optional reasoning engine to evaluate hooks, narrative arcs, and viral potential.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400 font-medium">Enable Reranker:</span>
            <Switch
              checked={rankerEnabled}
              onChange={(next) => onChange({ llm_ranker_enabled: next })}
              label="Enable LLM Reranking"
              testId="toggle-llm-ranker"
            />
          </div>
        </div>

        {/* Provider Selection */}
        <div className="space-y-3">
          <label className="text-xs font-semibold text-slate-300">Select LLM Adapter</label>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {[
              {
                id: "openrouter",
                name: "OpenRouter",
                badge: "Hosted Gateway",
                desc: "Zero-cost & frontier models behind one key",
                icon: <Zap className="h-4 w-4 text-amber-400" />,
              },
              {
                id: "openai_compatible",
                name: "Ollama / LM Studio",
                badge: "100% Local Server",
                desc: "Loopback OpenAI-compatible inference",
                icon: <Server className="h-4 w-4 text-emerald-400" />,
              },
              {
                id: "groq",
                name: "Groq LLM",
                badge: "LPU Cloud",
                desc: "Ultra low-latency Llama 3 models",
                icon: <Zap className="h-4 w-4 text-orange-400" />,
              },
            ].map((prov) => {
              const isSelected = llmProvider === prov.id;
              return (
                <button
                  key={prov.id}
                  type="button"
                  onClick={() => onChange({ llm_provider: prov.id })}
                  className={`p-3.5 rounded-xl border text-left transition-all relative ${
                    isSelected
                      ? "bg-indigo-950/40 border-indigo-500/60 ring-1 ring-indigo-500/40"
                      : "bg-slate-950/50 border-slate-800 hover:border-slate-700 hover:bg-slate-900/60"
                  }`}
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <div className="flex items-center gap-2">
                      {prov.icon}
                      <span className="text-xs font-semibold text-white">{prov.name}</span>
                    </div>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                      {prov.badge}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 leading-snug">{prov.desc}</p>
                </button>
              );
            })}
          </div>
        </div>

        {/* OpenRouter Configuration Panel */}
        {llmProvider === "openrouter" && (
          <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-4 space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-200 flex items-center gap-2">
                <Key className="h-4 w-4 text-amber-400" />
                <span>OpenRouter API Key (BYOK)</span>
              </span>
              <div className="flex items-center gap-2">
                {settings.llm_openrouter_api_key_configured && (
                  <span className="flex items-center gap-1 text-[11px] text-emerald-400 bg-emerald-950/50 px-2 py-0.5 rounded border border-emerald-800/40">
                    <CheckCircle2 className="h-3 w-3" />
                    <span>Configured: {settings.redacted_openrouter_api_key}</span>
                  </span>
                )}
                <a
                  href="https://openrouter.ai/keys"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[11px] text-laqta-400 hover:underline inline-flex items-center gap-1"
                >
                  <span>Get API Key</span>
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
            </div>

            <div className="flex flex-col sm:flex-row gap-2">
              <div className="relative flex-1">
                <input
                  type={showOpenRouterKey ? "text" : "password"}
                  placeholder={
                    settings.llm_openrouter_api_key_configured
                      ? "Enter new key to replace existing"
                      : "sk-or-v1-..."
                  }
                  value={draft.llm_openrouter_api_key ?? ""}
                  onChange={(e) => onChange({ llm_openrouter_api_key: e.target.value })}
                  className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-500 font-mono focus:border-indigo-500 focus:outline-none pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowOpenRouterKey(!showOpenRouterKey)}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
                  aria-label={showOpenRouterKey ? "Hide key" : "Show key"}
                >
                  {showOpenRouterKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>

              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  loading={verifying === "openrouter"}
                  onClick={() => handleTestKey("openrouter", draft.llm_openrouter_api_key)}
                >
                  Test Connection
                </Button>
                {settings.llm_openrouter_api_key_configured && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onChange({ llm_openrouter_api_key: "" })}
                    title="Remove stored key"
                  >
                    Clear Key
                  </Button>
                )}
              </div>
            </div>

            {/* Test result status */}
            {verifyResult["openrouter"] && (
              <div
                className={`p-2.5 rounded-lg border text-xs flex items-center justify-between ${
                  verifyResult["openrouter"]?.ok
                    ? "bg-emerald-950/40 border-emerald-800/40 text-emerald-300"
                    : "bg-red-950/40 border-red-800/40 text-red-300"
                }`}
              >
                <div className="flex items-center gap-2">
                  {verifyResult["openrouter"]?.ok ? (
                    <CheckCircle2 className="h-4 w-4 shrink-0" />
                  ) : (
                    <AlertTriangle className="h-4 w-4 shrink-0" />
                  )}
                  <span>{verifyResult["openrouter"]?.message}</span>
                </div>
                <span className="font-mono text-[11px] opacity-75">
                  {verifyResult["openrouter"]?.latency_ms} ms
                </span>
              </div>
            )}

            {/* Model Selection with Free Preset Chips */}
            <div className="space-y-2 pt-2 border-t border-slate-800/60">
              <label className="text-xs font-semibold text-slate-300">Model ID</label>
              <input
                type="text"
                value={draft.llm_openrouter_model ?? settings.llm_openrouter_model}
                onChange={(e) => onChange({ llm_openrouter_model: e.target.value })}
                className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white font-mono focus:border-indigo-500 focus:outline-none"
              />
              <div className="flex flex-wrap items-center gap-1.5 pt-1">
                <span className="text-[11px] text-slate-500">Zero-cost presets:</span>
                {[
                  "minimax/minimax-m3.1-flash:free",
                  "meta-llama/llama-3.3-70b-instruct:free",
                  "google/gemma-4-31b-it:free",
                  "liquid/lfm-2.5-2.6b:free",
                ].map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => onChange({ llm_openrouter_model: m })}
                    className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700/60 transition-colors"
                  >
                    {m.split("/")[1] || m}
                  </button>
                ))}
              </div>
            </div>

            {/* Hosted Opt-In confirmation */}
            <div className="flex items-center justify-between pt-2 border-t border-slate-800/60">
              <div className="max-w-xl">
                <span className="text-xs font-semibold text-slate-200">
                  Acknowledge Hosted Disclosure (Opt-in)
                </span>
                <p className="text-[11px] text-slate-400">
                  Required before sending candidate window transcripts to OpenRouter.
                </p>
              </div>
              <Switch
                checked={hostedOptIn}
                onChange={(next) => onChange({ llm_hosted_opt_in: next })}
                label="Hosted Opt-In"
                testId="toggle-hosted-opt-in"
              />
            </div>
          </div>
        )}

        {/* Local OpenAI-Compatible (Ollama / LM Studio) Configuration Panel */}
        {llmProvider === "openai_compatible" && (
          <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-4 space-y-4">
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-slate-200">Base URL</label>
                <div className="flex items-center gap-1.5">
                  <span className="text-[11px] text-slate-500">Presets:</span>
                  <button
                    type="button"
                    onClick={() => onChange({ llm_base_url: "http://127.0.0.1:11434/v1" })}
                    className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700"
                  >
                    Ollama (11434)
                  </button>
                  <button
                    type="button"
                    onClick={() => onChange({ llm_base_url: "http://127.0.0.1:1234/v1" })}
                    className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700"
                  >
                    LM Studio (1234)
                  </button>
                </div>
              </div>
              <input
                type="text"
                value={draft.llm_base_url ?? settings.llm_base_url}
                onChange={(e) => onChange({ llm_base_url: e.target.value })}
                className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white font-mono focus:border-indigo-500 focus:outline-none"
              />
            </div>

            <div className="space-y-2">
              <label className="text-xs font-semibold text-slate-200">Model Name</label>
              <input
                type="text"
                value={draft.llm_model ?? settings.llm_model}
                onChange={(e) => onChange({ llm_model: e.target.value })}
                className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white font-mono focus:border-indigo-500 focus:outline-none"
                placeholder="qwen2.5:7b-instruct"
              />
            </div>

            <div className="space-y-2 pt-2 border-t border-slate-800/60">
              <label className="text-xs font-semibold text-slate-200 flex items-center justify-between">
                <span>Optional Server API Key</span>
                {settings.llm_api_key_configured && (
                  <span className="text-[11px] text-emerald-400">
                    Configured ({settings.redacted_llm_api_key})
                  </span>
                )}
              </label>
              <div className="flex flex-col sm:flex-row gap-2">
                <div className="relative flex-1">
                  <input
                    type={showOpenAiKey ? "text" : "password"}
                    placeholder="Leave empty if local server requires no authorization"
                    value={draft.llm_api_key ?? ""}
                    onChange={(e) => onChange({ llm_api_key: e.target.value })}
                    className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white font-mono focus:border-indigo-500 focus:outline-none pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowOpenAiKey(!showOpenAiKey)}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
                  >
                    {showOpenAiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                <Button
                  variant="secondary"
                  size="sm"
                  loading={verifying === "openai_compatible"}
                  onClick={() =>
                    handleTestKey(
                      "openai_compatible",
                      draft.llm_api_key,
                      draft.llm_base_url ?? settings.llm_base_url,
                      draft.llm_model ?? settings.llm_model,
                    )
                  }
                >
                  Test Connection
                </Button>
              </div>

              {verifyResult["openai_compatible"] && (
                <div
                  className={`p-2.5 rounded-lg border text-xs flex items-center justify-between ${
                    verifyResult["openai_compatible"]?.ok
                      ? "bg-emerald-950/40 border-emerald-800/40 text-emerald-300"
                      : "bg-red-950/40 border-red-800/40 text-red-300"
                  }`}
                >
                  <span>{verifyResult["openai_compatible"]?.message}</span>
                  <span className="font-mono text-[11px]">
                    {verifyResult["openai_compatible"]?.latency_ms} ms
                  </span>
                </div>
              )}
            </div>
          </div>
        )}
      </section>

      {/* 3. Cloud Speech Recognition (Groq Whisper & AssemblyAI BYOK) */}
      <section className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-6">
        <div className="flex items-center gap-2.5 pb-4 border-b border-slate-800">
          <Zap className="h-5 w-5 text-orange-400" />
          <div>
            <h2 className="text-sm font-semibold text-white">Cloud Speech Recognition (BYOK)</h2>
            <p className="text-xs text-slate-400">
              High-speed cloud transcription backends for large files without high CPU load.
            </p>
          </div>
        </div>

        {/* Groq Whisper */}
        <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-4 space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-200 flex items-center gap-2">
              <Key className="h-4 w-4 text-orange-400" />
              <span>Groq Cloud Whisper API Key</span>
            </span>
            <div className="flex items-center gap-2">
              {settings.groq_api_key_configured && (
                <span className="flex items-center gap-1 text-[11px] text-emerald-400 bg-emerald-950/50 px-2 py-0.5 rounded border border-emerald-800/40">
                  <CheckCircle2 className="h-3 w-3" />
                  <span>Configured: {settings.redacted_groq_api_key}</span>
                </span>
              )}
              <a
                href="https://console.groq.com/keys"
                target="_blank"
                rel="noopener noreferrer"
                className="text-[11px] text-laqta-400 hover:underline inline-flex items-center gap-1"
              >
                <span>Groq Console</span>
                <ExternalLink className="h-3 w-3" />
              </a>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row gap-2">
            <div className="relative flex-1">
              <input
                type={showGroqKey ? "text" : "password"}
                placeholder={
                  settings.groq_api_key_configured ? "Enter new key to replace existing" : "gsk_..."
                }
                value={draft.groq_api_key ?? ""}
                onChange={(e) => onChange({ groq_api_key: e.target.value })}
                className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white font-mono focus:border-indigo-500 focus:outline-none pr-10"
              />
              <button
                type="button"
                onClick={() => setShowGroqKey(!showGroqKey)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
              >
                {showGroqKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                loading={verifying === "groq"}
                onClick={() => handleTestKey("groq", draft.groq_api_key)}
              >
                Test Key
              </Button>
              {settings.groq_api_key_configured && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onChange({ groq_api_key: "" })}
                  title="Remove stored key"
                >
                  Clear Key
                </Button>
              )}
            </div>
          </div>

          {verifyResult["groq"] && (
            <div
              className={`p-2.5 rounded-lg border text-xs flex items-center justify-between ${
                verifyResult["groq"]?.ok
                  ? "bg-emerald-950/40 border-emerald-800/40 text-emerald-300"
                  : "bg-red-950/40 border-red-800/40 text-red-300"
              }`}
            >
              <span>{verifyResult["groq"]?.message}</span>
              <span className="font-mono text-[11px]">{verifyResult["groq"]?.latency_ms} ms</span>
            </div>
          )}

          <div className="space-y-1 pt-2 border-t border-slate-800/60">
            <label className="text-xs font-semibold text-slate-300">Groq Whisper Model</label>
            <select
              value={draft.groq_model ?? settings.groq_model}
              onChange={(e) => onChange({ groq_model: e.target.value })}
              className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:border-indigo-500 focus:outline-none cursor-pointer"
            >
              <option value="whisper-large-v3-turbo">
                whisper-large-v3-turbo (Fastest, High Accuracy)
              </option>
              <option value="whisper-large-v3">whisper-large-v3 (Standard)</option>
            </select>
          </div>
        </div>

        {/* AssemblyAI & Hugging Face */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* AssemblyAI */}
          <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-200">AssemblyAI Key</span>
              {settings.assemblyai_api_key_configured && (
                <span className="text-[10px] text-emerald-400">Configured</span>
              )}
            </div>
            <div className="relative">
              <input
                type={showAssemblyAiKey ? "text" : "password"}
                placeholder="AssemblyAI Key..."
                value={draft.assemblyai_api_key ?? ""}
                onChange={(e) => onChange({ assemblyai_api_key: e.target.value })}
                className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white font-mono focus:border-indigo-500 focus:outline-none pr-8"
              />
              <button
                type="button"
                onClick={() => setShowAssemblyAiKey(!showAssemblyAiKey)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
              >
                {showAssemblyAiKey ? (
                  <EyeOff className="h-3.5 w-3.5" />
                ) : (
                  <Eye className="h-3.5 w-3.5" />
                )}
              </button>
            </div>
            <Button
              variant="secondary"
              size="sm"
              loading={verifying === "assemblyai"}
              onClick={() => handleTestKey("assemblyai", draft.assemblyai_api_key)}
              className="w-full"
            >
              Test AssemblyAI
            </Button>
            {verifyResult["assemblyai"] && (
              <p
                className={`text-[11px] ${
                  verifyResult["assemblyai"]?.ok ? "text-emerald-400" : "text-red-400"
                }`}
              >
                {verifyResult["assemblyai"]?.message}
              </p>
            )}
          </div>

          {/* Hugging Face Token */}
          <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-200">Hugging Face Token</span>
              {settings.hf_token_configured && (
                <span className="text-[10px] text-emerald-400">Configured</span>
              )}
            </div>
            <div className="relative">
              <input
                type={showHfToken ? "text" : "password"}
                placeholder="hf_..."
                value={draft.hf_token ?? ""}
                onChange={(e) => onChange({ hf_token: e.target.value })}
                className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white font-mono focus:border-indigo-500 focus:outline-none pr-8"
              />
              <button
                type="button"
                onClick={() => setShowHfToken(!showHfToken)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
              >
                {showHfToken ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
              </button>
            </div>
            <Button
              variant="secondary"
              size="sm"
              loading={verifying === "huggingface"}
              onClick={() => handleTestKey("huggingface", draft.hf_token)}
              className="w-full"
            >
              Test Hugging Face
            </Button>
            {verifyResult["huggingface"] && (
              <p
                className={`text-[11px] ${
                  verifyResult["huggingface"]?.ok ? "text-emerald-400" : "text-red-400"
                }`}
              >
                {verifyResult["huggingface"]?.message}
              </p>
            )}
            <p className="text-[10px] text-slate-500 leading-tight">
              Used when downloading gated or rate-limited Whisper model weights from Hugging Face
              Hub.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
};
