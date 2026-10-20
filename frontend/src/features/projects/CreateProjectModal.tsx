import React, { useState } from "react";
import { FolderPlus } from "lucide-react";
import { Modal } from "../../components/ui/Modal";
import { Button } from "../../components/ui/Button";

interface CreateProjectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (name: string) => Promise<void>;
}

export const CreateProjectModal: React.FC<CreateProjectModalProps> = ({
  isOpen,
  onClose,
  onCreate,
}) => {
  const [name, setName] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Please enter a project name.");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      await onCreate(trimmed);
      setName("");
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create project.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Create New Project"
      description="Enter a name for a new local project workspace."
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="project-name" className="block text-xs font-medium text-slate-300 mb-1.5">
            Project Name
          </label>
          <input
            id="project-name"
            type="text"
            data-autofocus
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              if (error) setError(null);
            }}
            placeholder="e.g. Tech Talk Podcast #04"
            className="w-full px-3.5 py-2.5 bg-obsidian-950 border border-slate-800 rounded-xl text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-laqta-500 focus:border-transparent transition-all"
            disabled={isSubmitting}
          />
          <p className="flex items-center space-x-1.5 mt-2 text-[11px] text-slate-500">
            <FolderPlus className="h-3.5 w-3.5 text-laqta-400" aria-hidden="true" />
            <span>Stored locally on this device only.</span>
          </p>
        </div>

        <div aria-live="polite">
          {error && (
            <div
              role="alert"
              className="text-xs text-red-400 bg-red-950/50 border border-red-800/50 rounded-lg p-2.5"
            >
              {error}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end space-x-3 pt-2">
          <Button variant="ghost" size="sm" onClick={onClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button
            type="submit"
            size="sm"
            loading={isSubmitting}
            disabled={isSubmitting || !name.trim()}
          >
            {isSubmitting ? "Creating..." : "Create Project"}
          </Button>
        </div>
      </form>
    </Modal>
  );
};

export default CreateProjectModal;
