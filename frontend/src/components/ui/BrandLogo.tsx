import React from "react";
import { LaqtaMark } from "./LaqtaMark";
import { BRAND } from "../../lib/brand";

interface BrandLogoProps {
  size?: "sm" | "md" | "lg";
  showSubtitle?: boolean;
  showText?: boolean;
  className?: string;
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
 * The Laqta wordmark.
 *
 * `لقطّة` ("a take / a cut") is the Arabic name of the product; the badge
 * keeps the bilingual identity visible next to the Latin wordmark.
 */
export const BrandLogo: React.FC<BrandLogoProps> = ({
  size = "md",
  showSubtitle = true,
  showText = true,
  className = "",
}) => {
  const markSize = MARK_SIZES[size];

  return (
    <div className={`flex items-center gap-3 select-none ${className}`}>
      <span
        className="relative flex-shrink-0 rounded-xl shadow-neon-purple"
        data-testid="brand-logo-icon"
      >
        <LaqtaMark size={markSize} title="Laqta logo" />
      </span>

      {showText && (
        <div className="flex flex-col">
          <div className="flex items-center gap-1.5">
            <span
              className={`${TITLE_SIZES[size]} font-bold tracking-tight text-white flex items-center`}
            >
              {BRAND.name}
            </span>
            <span
              dir="rtl"
              className="text-xs font-semibold px-1.5 py-0.5 rounded bg-laqta-950/80 text-laqta-200 border border-laqta-800/50"
            >
              {BRAND.nameArabic}
            </span>
          </div>
          {showSubtitle && (
            <span className="text-[11px] text-slate-400 tracking-wide font-medium">
              Long Videos <span className="text-neon-cyan">→</span> Viral Shorts
            </span>
          )}
        </div>
      )}
    </div>
  );
};

export default BrandLogo;
