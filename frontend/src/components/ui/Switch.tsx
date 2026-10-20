import React from "react";

export interface SwitchProps {
  checked: boolean;
  onChange: (next: boolean) => void;
  /** Accessible name for the switch. */
  label: string;
  /** Test hook + DOM id. */
  testId?: string;
  disabled?: boolean;
}

/**
 * Shared switch used by every inspector toggle so the on/off affordance
 * looks and behaves the same across the Edit, Captions and Export tabs.
 */
export const Switch: React.FC<SwitchProps> = ({
  checked,
  onChange,
  label,
  testId,
  disabled = false,
}) => (
  <button
    type="button"
    role="switch"
    aria-checked={checked}
    aria-label={label}
    onClick={() => onChange(!checked)}
    disabled={disabled}
    className={`relative w-11 h-6 shrink-0 rounded-full border transition-colors duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-laqta-400 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer ${
      checked
        ? "bg-neon-cyan/90 border-neon-cyan shadow-neon-cyan"
        : "bg-slate-800 border-slate-700 hover:bg-slate-700"
    }`}
    data-testid={testId}
  >
    <span
      className={`absolute top-1/2 -translate-y-1/2 h-4 w-4 rounded-full bg-obsidian-950 shadow-md transition-transform duration-200 ease-out-expo ${
        checked ? "translate-x-[22px]" : "translate-x-[3px]"
      }`}
      aria-hidden="true"
    />
  </button>
);

export default Switch;
