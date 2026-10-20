import React from "react";

export const LoadingSkeleton: React.FC = () => {
  return (
    <div
      className="space-y-6 animate-pulse"
      role="status"
      aria-busy="true"
      aria-label="Loading workspace"
      data-testid="loading-skeleton"
    >
      {/* Privacy banner skeleton */}
      <div className="h-24 bg-slate-900/60 border border-slate-800 rounded-xl"></div>

      {/* Capabilities card skeleton */}
      <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-5 space-y-4">
        <div className="h-4 w-48 bg-slate-800 rounded"></div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="h-24 bg-slate-800/40 rounded-lg"></div>
          <div className="h-24 bg-slate-800/40 rounded-lg"></div>
          <div className="h-24 bg-slate-800/40 rounded-lg"></div>
          <div className="h-24 bg-slate-800/40 rounded-lg"></div>
        </div>
      </div>

      {/* Main content skeleton */}
      <div className="h-80 bg-slate-900/30 border border-slate-800 rounded-2xl flex flex-col items-center justify-center space-y-3">
        <div className="h-12 w-12 rounded-xl bg-slate-800"></div>
        <div className="h-5 w-40 bg-slate-800 rounded"></div>
        <div className="h-4 w-72 bg-slate-800/60 rounded"></div>
      </div>
    </div>
  );
};
