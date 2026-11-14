import React from "react";
import { LaqtaMark, LaqtaMarkVariant } from "./LaqtaMark";
import { BRAND } from "../../lib/brand";

interface BrandLogoProps {
  size?: "sm" | "md" | "lg";
  showSubtitle?: boolean;
  showText?: boolean;
  className?: string;
  theme?: "dark" | "light";
  markVariant?: LaqtaMarkVariant;
}

const MARK_SIZES: Record<NonNullable<BrandLogoProps["size"]>, number> = {
  sm: 28,
  md: 36,
  lg: 48,
};

const TITLE_SIZES: Record<NonNullable<BrandLogoProps["size"]>, string> = {
  sm: "text-lg",
  md: "text-xl",
  lg: "text-2xl",
};

/**
 * Official Laqta Brand Logo component.
 *
 * Integrates the official Laqta vector mark, Latin wordmark, Arabic badge ("لقطة"),
 * and official tagline ("Long Videos to Viral Shorts").
 */
export const BrandLogo: React.FC<BrandLogoProps> = ({
  size = "md",
  showSubtitle = true,
  showText = true,
  className = "",
  theme = "dark",
  markVariant = "badge",
}) => {
  const markSize = MARK_SIZES[size];
  const isDark = theme === "dark";

  return (
    <div className={`flex items-center gap-3 select-none ${className}`}>
      <span
        className="relative flex-shrink-0 rounded-xl shadow-neon-purple"
        data-testid="brand-logo-icon"
      >
        <LaqtaMark size={markSize} title="Laqta logo" variant={markVariant} />
      </span>

      {showText && (
        <div className="flex flex-col">
          <div className="flex items-center gap-1.5">
            <span
              className={`${TITLE_SIZES[size]} font-extrabold tracking-tight flex items-center ${
                isDark ? "text-white" : "text-obsidian-900"
              }`}
            >
              {BRAND.name}
            </span>
            <span
              dir="rtl"
              className="text-xs font-semibold px-1.5 py-0.5 rounded bg-purple-950/80 text-laqta-200 border border-purple-800/50"
            >
              {BRAND.nameArabic}
            </span>
          </div>
          {showSubtitle && (
            <span
              className={`text-[11px] tracking-wide font-medium ${
                isDark ? "text-slate-400" : "text-slate-600"
              }`}
            >
              Long Videos <span className="text-neon-cyan font-bold">to</span> Viral Shorts
            </span>
          )}
        </div>
      )}
    </div>
  );
};

export default BrandLogo;
