/**
 * Shared display formatters.
 *
 * Every value rendered here is derived from real backend data (media asset
 * metadata, job timestamps, file sizes). Nothing is estimated or invented.
 */

/** `mm:ss` for short clips, `h:mm:ss` for long ones. */
export function formatDurationMs(ms: number): string {
  if (!ms || ms <= 0) return "00:00";
  const totalSeconds = Math.floor(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
  }
  return `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
}

/** Compact human duration, e.g. `48m`, `1h 12m`. */
export function formatDurationHuman(ms: number): string {
  if (!ms || ms <= 0) return "0m";
  const totalMinutes = Math.round(ms / 60000);
  if (totalMinutes < 60) return `${totalMinutes}m`;
  const hours = Math.floor(totalMinutes / 60);
  const mins = totalMinutes % 60;
  return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
}

/** Binary byte sizes with a single decimal for KB and above. */
export function formatBytes(bytes: number): string {
  if (!bytes || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / Math.pow(1024, exponent);
  return `${value.toFixed(exponent > 1 ? 1 : 0)} ${units[exponent]}`;
}

/**
 * Relative time for "last updated" labels.
 * Falls back to an absolute date for anything older than ~4 weeks.
 */
export function formatRelativeTime(
  isoDate: string | null | undefined,
  now: number = Date.now(),
): string {
  if (!isoDate) return "unknown";
  const timestamp = new Date(isoDate).getTime();
  if (Number.isNaN(timestamp)) return "unknown";

  const diffSeconds = Math.round((now - timestamp) / 1000);
  if (diffSeconds < 60) return "just now";

  const minutes = Math.floor(diffSeconds / 60);
  if (minutes < 60) return `${minutes} min ago`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return hours === 1 ? "1 hour ago" : `${hours} hours ago`;

  const days = Math.floor(hours / 24);
  if (days === 1) return "yesterday";
  if (days < 7) return `${days} days ago`;

  const weeks = Math.floor(days / 7);
  if (weeks < 5) return weeks === 1 ? "1 week ago" : `${weeks} weeks ago`;

  return new Date(isoDate).toLocaleDateString();
}

/** Clean platform markers (>> / &gt;&gt; / >), HTML entities, and redundant whitespace. */
export function cleanDisplayText(text?: string | null): string {
  if (!text) return "";
  return text
    .replace(/&gt;&gt;/gi, "")
    .replace(/&amp;/gi, "&")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/>>/g, "")
    .replace(/^\s*[>»]+\s*/g, "")
    .replace(/\s+/g, " ")
    .trim();
}
