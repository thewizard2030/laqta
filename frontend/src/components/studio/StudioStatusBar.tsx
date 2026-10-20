import React from "react";
import { CheckCircle2, CircleDashed, Sparkles, HardDrive } from "lucide-react";

interface StudioStatusBarProps {
  hasMedia?: boolean;
  hasTranscript?: boolean;
  clipCount?: number;
  mediaDetails?: string | null;
  storageWritable?: boolean;
}

/** One step of the local pipeline shown in the persistent status bar. */
const PipelineStep: React.FC<{
  done: boolean;
  label: string;
  pendingLabel?: string;
  icon: React.ReactNode;
  doneIcon: React.ReactNode;
  accent?: "cyan" | "emerald";
  title?: string;
}> = ({ done, label, pendingLabel, icon, doneIcon, accent = "emerald", title }) => {
  const doneColor = accent === "cyan" ? "text-neon-cyan" : "text-neon-emerald";
  return (
    <div
      className="flex items-center gap-1.5 flex-shrink-0"
      title={title}
      data-state={done ? "done" : "pending"}
    >
      {done ? (
        <span className={doneColor}>{doneIcon}</span>
      ) : (
        <span className="text-slate-600">{icon}</span>
      )}
      <span className={done ? "text-slate-200" : "text-slate-400"}>
        {done ? label : (pendingLabel ?? label)}
      </span>
    </div>
  );
};

export const StudioStatusBar: React.FC<StudioStatusBarProps> = ({
  hasMedia = false,
  hasTranscript = false,
  clipCount = 0,
  mediaDetails = null,
  storageWritable = true,
}) => {
  return (
    <footer
      className="h-9 shrink-0 border-t border-slate-800/80 bg-obsidian-900/70 backdrop-blur-md px-3 sm:px-4 flex items-center justify-between text-[11px] text-slate-400 select-none z-20"
      data-testid="studio-status-bar"
    >
      {/* Left Pipeline Milestones — announced politely on change */}
      <div
        className="flex items-center gap-2 sm:gap-3 overflow-x-auto min-w-0"
        role="status"
        aria-live="polite"
        aria-label="Pipeline status"
      >
        {/* Milestone 1: Video Status */}
        <PipelineStep
          done={hasMedia}
          label="Video loaded"
          pendingLabel="No video loaded"
          title={mediaDetails || undefined}
          icon={<CircleDashed className="h-3.5 w-3.5" aria-hidden="true" />}
          doneIcon={<CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />}
        />

        <span className="h-3 w-px bg-slate-800 shrink-0 hidden sm:block" aria-hidden="true" />

        {/* Milestone 2: Transcription Status */}
        <PipelineStep
          done={hasTranscript}
          label="Transcription completed"
          pendingLabel="Awaiting transcription"
          icon={<CircleDashed className="h-3.5 w-3.5" aria-hidden="true" />}
          doneIcon={<CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />}
        />

        <span className="h-3 w-px bg-slate-800 shrink-0 hidden md:block" aria-hidden="true" />

        {/* Milestone 3: Clips Generated */}
        <div className="hidden md:flex items-center gap-1.5 flex-shrink-0">
          {clipCount > 0 ? (
            <>
              <CheckCircle2 className="h-3.5 w-3.5 text-neon-cyan" aria-hidden="true" />
              <span className="text-slate-200 font-medium">{clipCount} clips generated</span>
            </>
          ) : (
            <>
              <CircleDashed className="h-3.5 w-3.5 text-slate-600" aria-hidden="true" />
              <span className="text-slate-400">0 clips generated</span>
            </>
          )}
        </div>

        <span className="h-3 w-px bg-slate-800 shrink-0 hidden lg:block" aria-hidden="true" />

        {/* Storage State Indicator */}
        <div className="hidden lg:flex items-center gap-1.5 flex-shrink-0">
          <HardDrive
            className={`h-3.5 w-3.5 ${storageWritable ? "text-neon-emerald" : "text-amber-400"}`}
            aria-hidden="true"
          />
          <span className="text-slate-400">
            {storageWritable ? "Storage: Ready" : "Storage: Read-Only"}
          </span>
        </div>
      </div>

      {/* Right Brand Motto */}
      <div className="flex items-center gap-2 text-slate-400 pl-4 flex-shrink-0">
        <Sparkles className="h-3 w-3 text-laqta-200" aria-hidden="true" />
        <span className="italic tracking-wide hidden sm:inline">Better Clips. Bigger Stories.</span>
        <div
          className="h-3 w-3 rounded-full bg-gradient-to-tr from-laqta-600 to-cyan-400 flex items-center justify-center p-0.5 ml-1"
          aria-hidden="true"
        >
          <div className="h-full w-full rounded-full bg-obsidian-950"></div>
        </div>
      </div>
    </footer>
  );
};
