import React, { useState } from "react";
import { PlusCircle, Video, Sparkles, Languages, Info } from "lucide-react";
import { LaqtaMark } from "./ui/LaqtaMark";

interface EmptyStateProps {
  onCreateProject?: () => void;
}

export const EmptyState: React.FC<EmptyStateProps> = ({ onCreateProject }) => {
  const [showInfoModal, setShowInfoModal] = useState(false);

  return (
    <div className="mx-auto w-full max-w-[1500px] bg-slate-900/40 border border-slate-800 rounded-2xl p-6 sm:p-10 text-center relative overflow-hidden">
      {/* Background glow decoration */}
      <div
        aria-hidden="true"
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-laqta-600/5 rounded-full blur-3xl pointer-events-none"
      />

      <div className="relative z-10 max-w-2xl mx-auto flex flex-col items-center">
        <div className="mb-5">
          <LaqtaMark size={56} title="Laqta" />
        </div>

        <h3 className="text-xl sm:text-2xl font-bold text-white tracking-tight">No projects yet</h3>
        <p className="text-sm text-slate-400 mt-2 leading-relaxed">
          Create a project to import your long-form video. Laqta will transcribe dialogue, extract
          candidate segments with explainable scoring, and render vertical Shorts locally on your
          device.
        </p>

        <div className="mt-6 flex flex-col sm:flex-row items-center gap-3">
          <button
            onClick={() => {
              if (onCreateProject) {
                onCreateProject();
              } else {
                setShowInfoModal(true);
              }
            }}
            className="w-full sm:w-auto inline-flex items-center justify-center space-x-2 px-5 py-2.5 rounded-xl laqta-gradient-surface hover:brightness-110 text-white font-medium text-sm shadow-laqta-glow transition-[filter] duration-200 focus:outline-none focus:ring-2 focus:ring-laqta-400 focus:ring-offset-2 focus:ring-offset-slate-950 cursor-pointer"
          >
            <PlusCircle className="h-4 w-4" />
            <span>Create New Project</span>
          </button>
        </div>

        {/* Informational note when clicking Create Project without a handler */}
        {showInfoModal && (
          <div className="mt-6 p-4 rounded-xl bg-slate-950/90 border border-slate-700 text-left w-full animate-fadeIn shadow-xl">
            <div className="flex items-start justify-between">
              <div className="flex items-center space-x-2 text-indigo-400 font-semibold text-xs">
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

        {/* Pipeline feature breakdown */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5 mt-10 w-full text-left">
          <div className="bg-slate-950/40 border border-slate-800/80 rounded-xl p-4 hover:border-slate-700/80 transition-colors">
            <div className="flex items-center space-x-2 text-xs font-semibold text-slate-200 mb-1">
              <Video className="h-3.5 w-3.5 text-indigo-400" />
              <span>1. Local Media Import</span>
            </div>
            <p className="text-xs text-slate-400 leading-normal">
              MP4, MOV, MKV, and WebM with file signature verification and FFprobe inspection.
            </p>
          </div>

          <div className="bg-slate-950/40 border border-slate-800/80 rounded-xl p-4 hover:border-slate-700/80 transition-colors">
            <div className="flex items-center space-x-2 text-xs font-semibold text-slate-200 mb-1">
              <Sparkles className="h-3.5 w-3.5 text-laqta-400" />
              <span>2. Explainable CPS</span>
            </div>
            <p className="text-xs text-slate-400 leading-normal">
              Heuristic Clip Potential Score (0–100) citing exact transcript evidence and clear
              component weights.
            </p>
          </div>

          <div className="bg-slate-950/40 border border-slate-800/80 rounded-xl p-4 hover:border-slate-700/80 transition-colors">
            <div className="flex items-center space-x-2 text-xs font-semibold text-slate-200 mb-1">
              <Languages className="h-3.5 w-3.5 text-emerald-400" />
              <span>3. Arabic & English UX</span>
            </div>
            <p className="text-xs text-slate-400 leading-normal">
              Dedicated RTL subtitle layout, punctuation tests, and local 1080×1920 MP4 export.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
