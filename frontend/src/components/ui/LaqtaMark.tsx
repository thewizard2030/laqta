import React from "react";

interface LaqtaMarkProps {
  /** Rendered width/height in pixels. */
  size?: number;
  className?: string;
  /**
   * Accessible name. When the mark sits next to a visible wordmark the
   * caller should pass `""` so the logo is not announced twice.
   */
  title?: string;
}

/**
 * The Laqta mark.
 *
 * A rounded "L" monogram cut from a violet-to-cyan gradient: the vertical
 * stem is the timeline, the horizontal foot is the cut, and the diagonal
 * notch on the shoulder mirrors the playback wedge of the old Qatta mark.
 * It is inline SVG so it stays crisp at every size and in both themes.
 */
export const LaqtaMark: React.FC<LaqtaMarkProps> = ({
  size = 36,
  className = "",
  title = "Laqta",
}) => {
  const gradientId = `laqta-mark-${size}`;

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      role={title ? "img" : "presentation"}
      aria-label={title || undefined}
      aria-hidden={title ? undefined : true}
      focusable="false"
      className={className}
      data-testid="laqta-mark"
    >
      {title && <title>{title}</title>}
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#8b5cf6" />
          <stop offset="55%" stopColor="#7c4dff" />
          <stop offset="100%" stopColor="#22d3ee" />
        </linearGradient>
      </defs>

      {/* Badge */}
      <rect width="48" height="48" rx="14" fill={`url(#${gradientId})`} />

      {/* Diagonal "cut" notch on the shoulder */}
      <path d="M48 12 L36 12 L48 26 Z" fill="#070A11" fillOpacity="0.28" />

      {/* L monogram: the stem is the timeline, the foot is the cut. */}
      <path d="M13 11 H21 V27 H35 V35 H13 Z" fill="#FFFFFF" />

      {/* Playback wedge in the counter of the L */}
      <path d="M25 12.5 L33 17 L25 21.5 Z" fill="#FFFFFF" fillOpacity="0.92" />
    </svg>
  );
};

export default LaqtaMark;
