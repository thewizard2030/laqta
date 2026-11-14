import React from "react";
import { LaqtaMark } from "./ui/LaqtaMark";

export const LoadingSkeleton: React.FC = () => {
  return (
    <div
      className="space-y-6"
      role="status"
      aria-busy="true"
      aria-label="Loading workspace"
      data-testid="loading-skeleton"
    >
      {/* Brand Startup Shimmer Card */}
      <div className="bg-obsidian-900/60 border border-slate-800/80 rounded-2xl p-8 flex flex-col items-center justify-center text-center relative overflow-hidden">
        <div
          aria-hidden="true"
          className="absolute -top-12 left-1/2 -translate-x-1/2 w-72 h-72 bg-laqta-600/10 rounded-full blur-3xl pointer-events-none"
        />

        <div className="relative z-10 flex flex-col items-center space-y-4 max-w-sm">
          <div className="p-1 rounded-2xl bg-obsidian-950/80 border border-purple-500/30 shadow-neon-purple animate-pulse">
            <LaqtaMark size={56} title="Laqta logo" variant="badge" />
          </div>

          <div className="space-y-1.5 w-full">
            <div className="h-4 w-32 bg-slate-800/80 rounded-md mx-auto shimmer" />
            <div className="h-3 w-48 bg-slate-800/50 rounded-md mx-auto shimmer" />
          </div>

          <div className="h-1.5 w-full bg-obsidian-950 rounded-full overflow-hidden border border-slate-800/80 p-[1px] mt-2">
            <div className="h-full w-1/2 laqta-gradient-surface rounded-full animate-[sheen_1.6s_ease-in-out_infinite]" />
          </div>
        </div>
      </div>

      {/* Grid content skeletons */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="h-24 bg-obsidian-900/50 border border-slate-800/70 rounded-xl p-4 flex flex-col justify-between"
          >
            <div className="h-3 w-20 bg-slate-800/80 rounded shimmer" />
            <div className="h-6 w-14 bg-slate-800/60 rounded shimmer" />
          </div>
        ))}
      </div>
    </div>
  );
};
