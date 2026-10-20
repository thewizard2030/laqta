import React, { useEffect, useState } from "react";
import { FolderPlus, Loader2, Youtube } from "lucide-react";
import { Modal } from "../../components/ui/Modal";
import { Project } from "../../types/projects";

const NEW_WORKSPACE = "__new__";

interface YouTubeTargetModalProps {
  isOpen: boolean;
  projects: Project[];
  onClose: () => void;
  /** Resolve the workspace that should receive the download. */
  onResolveTarget: (projectId: string) => Promise<void>;
  isResolving?: boolean;
  error?: string | null;
}

/**
 * Workspace picker for a dashboard-level YouTube import.
 *
 * The backend queues URL ingestion into a concrete project, so the user has
 * to pick the destination workspace before the gated import dialog opens.
 */
export const YouTubeTargetModal: React.FC<YouTubeTargetModalProps> = ({
  isOpen,
  projects,
  onClose,
  onResolveTarget,
  isResolving = false,
  error = null,
}) => {
  const [selected, setSelected] = useState<string>(projects[0]?.id ?? NEW_WORKSPACE);

  useEffect(() => {
    if (isOpen) {
      setSelected(projects[0]?.id ?? NEW_WORKSPACE);
    }
  }, [isOpen, projects]);

  const handleContinue = async () => {
    await onResolveTarget(selected);
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Import from YouTube"
      description="Choose the workspace that receives the downloaded video."
      maxWidthClass="max-w-md"
    >
      <div className="space-y-4">
        <fieldset className="space-y-2">
          <legend className="sr-only">Target workspace</legend>
          {projects.map((project) => (
            <label
              key={project.id}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-xl border cursor-pointer transition ${
                selected === project.id
                  ? "border-purple-500/60 bg-purple-950/30"
                  : "border-slate-800/80 bg-obsidian-950/60 hover:border-slate-700"
              }`}
            >
              <input
                type="radio"
                name="youtube-target"
                value={project.id}
                checked={selected === project.id}
                onChange={() => setSelected(project.id)}
                className="h-3.5 w-3.5 accent-laqta-600"
              />
              <span className="min-w-0 flex-1">
                <span dir="auto" className="block text-xs font-semibold text-white truncate">
                  {project.name}
                </span>
                <span className="block text-[10px] text-slate-500">
                  {project.media_count} {project.media_count === 1 ? "video" : "videos"}
                </span>
              </span>
            </label>
          ))}

          <label
            className={`flex items-center gap-3 px-3 py-2.5 rounded-xl border cursor-pointer transition ${
              selected === NEW_WORKSPACE
                ? "border-purple-500/60 bg-purple-950/30"
                : "border-slate-800/80 bg-obsidian-950/60 hover:border-slate-700"
            }`}
          >
            <input
              type="radio"
              name="youtube-target"
              value={NEW_WORKSPACE}
              checked={selected === NEW_WORKSPACE}
              onChange={() => setSelected(NEW_WORKSPACE)}
              className="h-3.5 w-3.5 accent-laqta-600"
            />
            <FolderPlus className="h-4 w-4 text-laqta-400 shrink-0" aria-hidden="true" />
            <span className="text-xs font-semibold text-white">Create a new workspace</span>
          </label>
        </fieldset>

        {error && (
          <p
            role="alert"
            className="rounded-xl border border-red-800/60 bg-red-950/40 px-3 py-2 text-[11px] text-red-300"
          >
            {error}
          </p>
        )}

        <div className="flex items-center justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:text-white bg-slate-800/60 hover:bg-slate-700/60 border border-slate-700/60 transition cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => {
              void handleContinue();
            }}
            disabled={isResolving}
            className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold text-white bg-gradient-to-r from-laqta-600 to-indigo-600 hover:from-laqta-500 hover:to-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-laqta-600/25 transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
          >
            {isResolving ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
            ) : (
              <Youtube className="h-3.5 w-3.5" aria-hidden="true" />
            )}
            Continue
          </button>
        </div>
      </div>
    </Modal>
  );
};

export default YouTubeTargetModal;
