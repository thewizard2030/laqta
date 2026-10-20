import React, { useEffect } from "react";
import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";

export type ToastType = "error" | "success" | "info";

interface ToastProps {
  type: ToastType;
  message: string;
  onClose: () => void;
  /** Auto-dismiss after this many ms; 0 keeps the toast until dismissed. */
  autoDismissMs?: number;
}

const typeConfig: Record<
  ToastType,
  { icon: React.ReactNode; ring: string; iconClass: string; role: "alert" | "status" }
> = {
  error: {
    icon: <AlertCircle className="h-4 w-4" aria-hidden="true" />,
    ring: "border-red-800/70 bg-red-950/90 text-red-200",
    iconClass: "text-red-400",
    role: "alert",
  },
  success: {
    icon: <CheckCircle2 className="h-4 w-4" aria-hidden="true" />,
    ring: "border-emerald-800/70 bg-emerald-950/90 text-emerald-200",
    iconClass: "text-emerald-400",
    role: "status",
  },
  info: {
    icon: <Info className="h-4 w-4" aria-hidden="true" />,
    ring: "border-indigo-800/70 bg-indigo-950/90 text-indigo-200",
    iconClass: "text-indigo-400",
    role: "status",
  },
};

/**
 * Fixed, non-blocking notification. Errors announce with role="alert";
 * success/info announce politely. Replaces native `alert()` calls.
 */
export const Toast: React.FC<ToastProps> = ({ type, message, onClose, autoDismissMs = 0 }) => {
  const config = typeConfig[type];

  useEffect(() => {
    if (!autoDismissMs) return;
    const timer = window.setTimeout(onClose, autoDismissMs);
    return () => window.clearTimeout(timer);
  }, [autoDismissMs, onClose]);

  return (
    <div
      className="fixed bottom-12 right-4 z-[60] max-w-sm animate-fadeUp"
      style={{ pointerEvents: "none" }}
    >
      <div
        role={config.role}
        aria-live={config.role === "alert" ? "assertive" : "polite"}
        className={`flex items-start gap-2.5 px-4 py-3 rounded-xl border shadow-2xl backdrop-blur-md ${config.ring}`}
        style={{ pointerEvents: "auto" }}
      >
        <span className={`mt-0.5 shrink-0 ${config.iconClass}`}>{config.icon}</span>
        <p className="text-xs leading-relaxed whitespace-pre-wrap flex-1">{message}</p>
        <button
          onClick={onClose}
          aria-label="Dismiss notification"
          className="mt-0.5 shrink-0 text-current opacity-60 hover:opacity-100 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 rounded cursor-pointer"
        >
          <X className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
};
