import React from "react";
import { AlertTriangle } from "lucide-react";
import { Modal } from "./Modal";
import { Button } from "./Button";

interface ConfirmDialogProps {
  isOpen: boolean;
  onClose: () => void;
  /** Called when the user confirms. Rejection prop chains stay synchronous. */
  onConfirm: () => void;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  isConfirming?: boolean;
  /** Destructive (red) when true, informational (primary) otherwise. */
  isDestructive?: boolean;
}

/**
 * Shared confirmation dialog. Replaces native `window.confirm` so destructive
 * actions never leave the app's visual context and remain keyboard operable.
 */
export const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  isConfirming = false,
  isDestructive = false,
}) => {
  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title} maxWidthClass="max-w-md">
      <div className="space-y-5">
        <div className="flex items-start space-x-3">
          <div
            className={`p-2 rounded-lg border shrink-0 ${
              isDestructive
                ? "bg-red-950/60 border-red-800/60 text-red-400"
                : "bg-indigo-950/60 border-indigo-800/60 text-indigo-400"
            }`}
          >
            <AlertTriangle className="h-5 w-5" aria-hidden="true" />
          </div>
          <p className="text-xs text-slate-300 leading-relaxed pt-1.5">{message}</p>
        </div>
        <div className="flex items-center justify-end space-x-2.5 pt-1">
          <Button variant="ghost" size="sm" onClick={onClose}>
            {cancelLabel}
          </Button>
          <Button
            variant={isDestructive ? "danger" : "primary"}
            size="sm"
            loading={isConfirming}
            onClick={onConfirm}
            data-autofocus
          >
            {isConfirming ? "Working..." : confirmLabel}
          </Button>
        </div>
      </div>
    </Modal>
  );
};
