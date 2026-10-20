import React from "react";
import { Loader2 } from "lucide-react";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** When true, shows a spinner and disables the button. */
  loading?: boolean;
}

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    "bg-gradient-to-r from-laqta-600 to-indigo-600 hover:from-laqta-500 hover:to-indigo-500 text-white shadow-lg shadow-laqta-600/20",
  secondary: "bg-slate-800/60 hover:bg-slate-700/60 text-slate-200 border border-slate-700/60",
  ghost: "text-slate-400 hover:text-white hover:bg-slate-800/80",
  danger: "bg-red-950/60 hover:bg-red-900/80 text-red-300 border border-red-800/60",
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: "px-3 py-1.5 text-xs rounded-lg gap-1.5",
  md: "px-4 py-2.5 text-sm rounded-xl gap-2",
};

/**
 * Shared button primitive. Every variant ships a visible focus-visible ring so
 * keyboard focus is never lost — component consumers should not opt out of it.
 */
export const Button: React.FC<ButtonProps> = ({
  variant = "primary",
  size = "md",
  loading = false,
  disabled,
  className = "",
  children,
  type = "button",
  ...rest
}) => {
  const isDisabled = disabled || loading;
  return (
    <button
      type={type}
      disabled={isDisabled}
      aria-busy={loading || undefined}
      className={`inline-flex items-center justify-center font-semibold transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 focus-visible:ring-offset-2 focus-visible:ring-offset-obsidian-950 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed ${sizeClasses[size]} ${variantClasses[variant]} ${className}`}
      {...rest}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
      {children}
    </button>
  );
};
