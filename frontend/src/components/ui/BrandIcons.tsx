import React from "react";

/**
 * Brand marks for the two external platforms Laqta links to.
 *
 * Lucide v1 removed its brand icons (`Github`, `Youtube`) because they are
 * third-party trademarks. These two small inline SVGs replace them: the
 * marks are used to *identify* the platform a link goes to, which is their
 * intended use.
 *
 * Both render as `aria-hidden` by default — the surrounding link or button
 * always carries the accessible name.
 */

interface BrandIconProps {
  className?: string;
  /** Accessible name. Leave empty for a purely decorative mark. */
  title?: string;
}

export const GitHubIcon: React.FC<BrandIconProps> = ({ className = "h-4 w-4", title = "" }) => (
  <svg
    viewBox="0 0 24 24"
    fill="currentColor"
    className={className}
    role={title ? "img" : "presentation"}
    aria-label={title || undefined}
    aria-hidden={title ? undefined : true}
    focusable="false"
  >
    {title ? <title>{title}</title> : null}
    <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.017-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 4.18 18.1 3.586 18.1c-3.164 0-5.31-1.248-6.335-3.985-.23-.6-.945-1.087-1.545-1.087-.122 0-.547.077-.098.128.6.022 1.147.186 1.667.645.09.456.332.956.645 1.436.39 1.016.947 2.22 2.04 2.91.42.56.96 1.02 1.516 1.02H9.475c-.39 0-.79-.15-1.075-.45-.28-.3-.4-.75-.4-1.2 0-1.35.75-2.6 1.75-3.3 1-.7 2.25-1.05 3.6-1.05 1.35 0 2.55.35 3.6 1.05 1 .7 1.75 1.95 1.75 3.3 0 .45-.12.9-.4 1.2-.285.3-.685.45-1.075.45h-.05c.56 0 1.125-.41 1.515-1.02.44-.72.695-1.6.695-2.55 0-1.42-.465-2.65-1.36-3.6-.9-.95-2.13-1.35-3.6-1.35z" />
  </svg>
);

export const YouTubeIcon: React.FC<BrandIconProps> = ({ className = "h-4 w-4", title = "" }) => (
  <svg
    viewBox="0 0 24 24"
    fill="currentColor"
    className={className}
    role={title ? "img" : "presentation"}
    aria-label={title || undefined}
    aria-hidden={title ? undefined : true}
    focusable="false"
  >
    {title ? <title>{title}</title> : null}
    <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
  </svg>
);
