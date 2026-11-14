import React, { useId } from "react";

export type LaqtaMarkVariant = "badge" | "symbol" | "monochrome";

interface LaqtaMarkProps {
  /** Rendered width/height in pixels. Default is 36. */
  size?: number;
  className?: string;
  /**
   * Accessible name. When the mark sits next to a visible wordmark the
   * caller should pass `""` so the logo is not announced twice.
   */
  title?: string;
  /**
   * Visual variant:
   * - "badge": Official square gradient app icon with rounded corners and white elements
   * - "symbol": Standalone transparent mark with gradient L and accent cues
   * - "monochrome": Single-color clean vector mark
   */
  variant?: LaqtaMarkVariant;
}

/**
 * Official Laqta Mark.
 *
 * Direct vector implementation of the official Brand Kit geometry:
 * - Geometric "L" (timeline + cut)
 * - Play triangle (media playback)
 * - Three vertical frame cues (story frames)
 *
 * Vector source: `Laqta_Brand_Kit/svg/laqta-app-icon.svg` & `laqta-symbol.svg`
 */
export const LaqtaMark: React.FC<LaqtaMarkProps> = ({
  size = 36,
  className = "",
  title = "Laqta",
  variant = "badge",
}) => {
  const rawId = useId();
  const safeId = rawId.replace(/[^a-zA-Z0-9_-]/g, "");
  const bgGradId = `laqta-bg-${safeId}-${size}`;
  const markGradId = `laqta-mark-${safeId}-${size}`;
  const accentGradId = `laqta-accent-${safeId}-${size}`;

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 1024 1024"
      role={title ? "img" : "presentation"}
      aria-label={title || undefined}
      aria-hidden={title ? undefined : true}
      focusable="false"
      className={`shrink-0 ${className}`}
      data-testid="laqta-mark"
    >
      {title && <title>{title}</title>}
      <defs>
        {/* Official brand gradient for badge background: Violet -> Purple -> Cyan */}
        <linearGradient id={bgGradId} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#A72BFF" />
          <stop offset="48%" stopColor="#5637F5" />
          <stop offset="100%" stopColor="#00C9E8" />
        </linearGradient>

        {/* Gradient for standalone mark */}
        <linearGradient id={markGradId} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#B34CFF" />
          <stop offset="52%" stopColor="#6544F5" />
          <stop offset="100%" stopColor="#00CBEA" />
        </linearGradient>

        {/* Gradient for accent cues */}
        <linearGradient id={accentGradId} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#9B35FF" />
          <stop offset="100%" stopColor="#00CDEB" />
        </linearGradient>
      </defs>

      {variant === "badge" && (
        <>
          {/* Rounded gradient badge */}
          <rect width="1024" height="1024" rx="220" fill={`url(#${bgGradId})`} />
          {/* Diagonal cut shadow */}
          <path d="M560 0 H1024 V620 Z" fill="#09102E" opacity="0.12" />
          {/* Geometric L shape */}
          <path d="M270 240 H408 V648 H750 V786 H338 C300 786 270 756 270 718 Z" fill="#FFFFFF" />
          {/* Play triangle */}
          <path d="M492 350 L680 470 L492 590 Z" fill="#FFFFFF" />
          {/* Three frame cues */}
          <rect x="742" y="242" width="70" height="70" rx="15" fill="#FFFFFF" />
          <rect x="742" y="352" width="70" height="70" rx="15" fill="#FFFFFF" opacity="0.82" />
          <rect x="742" y="462" width="70" height="70" rx="15" fill="#FFFFFF" opacity="0.64" />
        </>
      )}

      {variant === "symbol" && (
        <g>
          {/* Gradient L mark */}
          <path
            d="M270 240 H408 V648 H750 V786 H338 C300 786 270 756 270 718 Z"
            fill={`url(#${markGradId})`}
          />
          {/* Play triangle */}
          <path d="M492 350 L680 470 L492 590 Z" fill="#FFFFFF" />
          {/* Three accent frame cues */}
          <rect x="742" y="242" width="70" height="70" rx="15" fill={`url(#${accentGradId})`} />
          <rect
            x="742"
            y="352"
            width="70"
            height="70"
            rx="15"
            fill={`url(#${accentGradId})`}
            opacity="0.82"
          />
          <rect
            x="742"
            y="462"
            width="70"
            height="70"
            rx="15"
            fill={`url(#${accentGradId})`}
            opacity="0.64"
          />
        </g>
      )}

      {variant === "monochrome" && (
        <g fill="currentColor">
          <path d="M270 240 H408 V648 H750 V786 H338 C300 786 270 756 270 718 Z" />
          <path d="M492 350 L680 470 L492 590 Z" />
          <rect x="742" y="242" width="70" height="70" rx="15" />
          <rect x="742" y="352" width="70" height="70" rx="15" opacity="0.82" />
          <rect x="742" y="462" width="70" height="70" rx="15" opacity="0.64" />
        </g>
      )}
    </svg>
  );
};

export default LaqtaMark;
