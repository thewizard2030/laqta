import React, { useState } from "react";
import { PlusCircle, Video, Sparkles, Languages, Info, Mic, Film, Scissors } from "lucide-react";
import { LaqtaMark } from "./ui/LaqtaMark";

export type EmptyStateType = "projects" | "media" | "clips" | "transcript";

interface EmptyStateProps {
  type?: EmptyStateType;
  title?: string;
  description?: string;
  onCreateProject?: () => void;
  onAction?: () => void;
  actionLabel?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  type = "projects",
  title,
  description,
  onCreateProject,
  onAction,
  actionLabel,
}) => {
  const [showInfoModal, setShowInfoModal] = useState(false);

  const config = {
    projects: {
      defaultTitle: "No projects yet",
      defaultDesc:
        "Create a project to import your long-form video. Laqta will transcribe dialogue, extract candidate segments with explainable scoring, and render vertical Shorts locally on your device.",
      defaultActionLabel: "Create New Project",
      icon: <LaqtaMark size={56} title="Laqta" variant="badge" />,
    },
    media: {
      defaultTitle: "No video imported",
      defaultDesc:
        "Import an MP4, MOV, MKV, or WebM video file into this workspace. Laqta will inspect media streams and prepare the audio for local transcription.",
      defaultActionLabel: "Import Video",
      icon: (
        <div className="h-14 w-14 rounded-2xl bg-purple-950/60 border border-purple-500/30 flex items-center justify-center text-neon-cyan shadow-sm">
          <Film className="h-7 w-7" />
        </div>
      ),
    },
    clips: {
      defaultTitle: "No discovered clips yet",
      defaultDesc:
        "Run the scoring pipeline to evaluate speech pacing, engagement hooks, and narrative cohesion. Every candidate includes full explainable scoring.",
      defaultActionLabel: "Analyze Video for Clips",
      icon: (
        <div className="h-14 w-14 rounded-2xl bg-purple-950/60 border border-purple-500/30 flex items-center justify-center text-laqta-400 shadow-sm">
          <Scissors className="h-7 w-7" />
        </div>
      ),
    },
    transcript: {
      defaultTitle: "No transcription results",
      defaultDesc:
        "Transcribe spoken dialogue into atomic utterances bounded by real acoustic pauses. Supports Arabic RTL layout and Arablish technical phrasing.",
      defaultActionLabel: "Start Transcription",
      icon: (
        <div className="h-14 w-14 rounded-2xl bg-purple-950/60 border border-purple-500/30 flex items-center justify-center text-neon-cyan shadow-sm">
          <Mic className="h-7 w-7" />
        </div>
      ),
    },
  }[type];

  const effectiveTitle = title || config.defaultTitle;
  const effectiveDesc = description || config.defaultDesc;
  const effectiveActionLabel = actionLabel || config.defaultActionLabel;
  const handlePrimaryClick = onAction || onCreateProject;

  return (
    <div
      className="mx-auto w-full max-w-[1500px] bg-obsidian-900/60 border border-slate-800/80 rounded-2xl p-6 sm:p-10 text-center relative overflow-hidden"
      data-testid={`empty-state-${type}`}
    >
      {/* Background brand glow */}
      <div
        aria-hidden="true"
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-laqta-600/5 rounded-full blur-3xl pointer-events-none"
      />

      <div className="relative z-10 max-w-2xl mx-auto flex flex-col items-center">
        <div className="mb-5">{config.icon}</div>

        <h3 className="text-xl sm:text-2xl font-bold text-white tracking-tight">
          {effectiveTitle}
        </h3>
        <p className="text-sm text-slate-400 mt-2 leading-relaxed">{effectiveDesc}</p>

        {handlePrimaryClick ? (
          <div className="mt-6 flex flex-col sm:flex-row items-center gap-3">
            <button
              onClick={handlePrimaryClick}
              className="w-full sm:w-auto inline-flex items-center justify-center space-x-2 px-5 py-2.5 rounded-xl laqta-gradient-surface hover:brightness-110 text-white font-medium text-sm shadow-laqta-glow transition-[filter] duration-200 focus:outline-none focus:ring-2 focus:ring-laqta-400 focus:ring-offset-2 focus:ring-offset-obsidian-950 cursor-pointer"
            >
              <PlusCircle className="h-4 w-4" />
              <span>{effectiveActionLabel}</span>
            </button>
          </div>
        ) : (
          <div className="mt-6">
            <button
              onClick={() => setShowInfoModal(true)}
              className="text-xs text-laqta-300 hover:text-white underline cursor-pointer"
            >
              Learn more about this step
            </button>
          </div>
        )}

        {showInfoModal && (
          <div className="mt-6 p-4 rounded-xl bg-obsidian-950/90 border border-slate-700 text-left w-full animate-fadeIn shadow-xl">
            <div className="flex items-start justify-between">
              <div className="flex items-center space-x-2 text-laqta-300 font-semibold text-xs">
                <Info className="h-4 w-4" />
                <span>Getting Started</span>
              </div>
              <button
                onClick={() => setShowInfoModal(false)}
                className="text-xs text-slate-400 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 rounded cursor-pointer"
              >
                Close
              </button>
            </div>
            <p className="text-xs text-slate-300 mt-2">
              Start by creating a project, then import a long-form local video file. Everything is
              processed on-device — nothing is uploaded.
            </p>
          </div>
        )}

        {/* Pipeline feature breakdown shown for projects empty state */}
        {type === "projects" && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5 mt-10 w-full text-left">
            <div className="bg-obsidian-950/50 border border-slate-800/80 rounded-xl p-4 hover:border-slate-700/80 transition-colors">
              <div className="flex items-center space-x-2 text-xs font-semibold text-slate-200 mb-1">
                <Video className="h-3.5 w-3.5 text-neon-cyan" />
                <span>1. Local Media Import</span>
              </div>
              <p className="text-xs text-slate-400 leading-normal">
                MP4, MOV, MKV, and WebM with file signature verification and FFprobe inspection.
              </p>
            </div>

            <div className="bg-obsidian-950/50 border border-slate-800/80 rounded-xl p-4 hover:border-slate-700/80 transition-colors">
              <div className="flex items-center space-x-2 text-xs font-semibold text-slate-200 mb-1">
                <Sparkles className="h-3.5 w-3.5 text-laqta-400" />
                <span>2. Explainable CPS</span>
              </div>
              <p className="text-xs text-slate-400 leading-normal">
                Heuristic Clip Potential Score (0–100) citing exact transcript evidence and clear
                component weights.
              </p>
            </div>

            <div className="bg-obsidian-950/50 border border-slate-800/80 rounded-xl p-4 hover:border-slate-700/80 transition-colors">
              <div className="flex items-center space-x-2 text-xs font-semibold text-slate-200 mb-1">
                <Languages className="h-3.5 w-3.5 text-neon-emerald" />
                <span>3. Arabic & English UX</span>
              </div>
              <p className="text-xs text-slate-400 leading-normal">
                Dedicated RTL subtitle layout, punctuation tests, and local 1080×1920 MP4 export.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default EmptyState;
