import React, { useCallback, useEffect, useRef } from "react";
import { X } from "lucide-react";

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** Heading text; used for the dialog's accessible name. */
  title: string;
  ariaLabelId?: string;
  /** Extra description for screen readers. */
  description?: string;
  /** Width class for the panel, e.g. "max-w-md". */
  maxWidthClass?: string;
  children: React.ReactNode;
}

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';

/**
 * Managed dialog: Escape-to-close, backdrop click-to-close, simple focus trap,
 * focus restore to the element that opened it, and body scroll lock.
 * All modals in the app must be rendered through this component.
 */
export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  title,
  ariaLabelId = "modal-title",
  description,
  maxWidthClass = "max-w-md",
  children,
}) => {
  const panelRef = useRef<HTMLDivElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);

  const handleClose = useCallback(() => {
    onClose();
    // Restore focus to the element that opened the dialog, after unmount.
    requestAnimationFrame(() => {
      openerRef.current?.focus?.();
    });
  }, [onClose]);

  useEffect(() => {
    if (!isOpen) return;

    openerRef.current = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    // Move focus into the dialog on open.
    requestAnimationFrame(() => {
      const panel = panelRef.current;
      if (!panel) return;
      const first =
        panel.querySelector<HTMLElement>("[data-autofocus]") ??
        panel.querySelector<HTMLElement>(FOCUSABLE_SELECTOR);
      first?.focus();
    });

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        handleClose();
        return;
      }
      if (e.key === "Tab" && panelRef.current) {
        const focusable = Array.from(
          panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        } else if (!panelRef.current.contains(document.activeElement)) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    document.addEventListener("keydown", handleKeyDown, true);
    return () => {
      document.removeEventListener("keydown", handleKeyDown, true);
      document.body.style.overflow = previousOverflow;
    };
  }, [isOpen, handleClose]);

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby={ariaLabelId}
      aria-describedby={description ? `${ariaLabelId}-desc` : undefined}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-obsidian-950/80 backdrop-blur-sm animate-fadeIn"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) handleClose();
      }}
    >
      <div
        ref={panelRef}
        className={`bg-obsidian-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden w-full ${maxWidthClass}`}
      >
        <div className="flex items-start justify-between px-6 py-4 border-b border-slate-800">
          <h3 id={ariaLabelId} dir="auto" className="text-base font-semibold text-white">
            {title}
          </h3>
          <button
            onClick={handleClose}
            className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400"
            aria-label="Close dialog"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>
        {description && (
          <p id={`${ariaLabelId}-desc`} className="sr-only">
            {description}
          </p>
        )}
        <div className="px-6 py-5">{children}</div>
      </div>
    </div>
  );
};
