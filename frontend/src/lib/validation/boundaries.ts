/**
 * Boundary-edit validation for candidate review (PRD §5 FR-04, §9).
 *
 * Validation happens in Python on the backend too (defense in depth), but the
 * UI must pre-validate so users see immediate, honest feedback. Ranges are
 * clamped to the source media duration and the configured min/max duration
 * (backend defaults 30-55 s). No invented values: an invalid edit is never
 * sent to the backend.
 */

export interface BoundaryBounds {
  minDurationMs: number; // backend default 30 s
  maxDurationMs: number; // backend default 55 s
  mediaDurationMs: number; // source duration from the probed asset
}

export interface BoundaryValidationOk {
  ok: true;
  startMs: number;
  endMs: number;
  durationMs: number;
}

export interface BoundaryValidationError {
  ok: false;
  field: "start" | "end" | "duration";
  message: string;
}

export type BoundaryValidationResult = BoundaryValidationOk | BoundaryValidationError;

export const DEFAULT_MIN_DURATION_MS = 30_000;
export const DEFAULT_MAX_DURATION_MS = 55_000;

export function validateBoundaryEdit(
  startMs: number | null,
  endMs: number | null,
  bounds: BoundaryBounds,
): BoundaryValidationResult {
  if (startMs === null || Number.isNaN(startMs)) {
    return { ok: false, field: "start", message: "Start time is required." };
  }
  if (endMs === null || Number.isNaN(endMs)) {
    return { ok: false, field: "end", message: "End time is required." };
  }
  if (startMs < 0) {
    return {
      ok: false,
      field: "start",
      message: "Start cannot be before the beginning of the video (0 ms).",
    };
  }
  if (endMs > bounds.mediaDurationMs) {
    return {
      ok: false,
      field: "end",
      message: `End extends beyond the source video (${bounds.mediaDurationMs} ms).`,
    };
  }
  if (endMs <= startMs) {
    return {
      ok: false,
      field: "end",
      message: "End must be after start.",
    };
  }
  const durationMs = endMs - startMs;
  if (durationMs < bounds.minDurationMs || durationMs > bounds.maxDurationMs) {
    return {
      ok: false,
      field: "duration",
      message:
        `Duration ${(durationMs / 1000).toFixed(1)} s is outside the configured ` +
        `${(bounds.minDurationMs / 1000).toFixed(0)}-` +
        `${(bounds.maxDurationMs / 1000).toFixed(0)} s range.`,
    };
  }
  return { ok: true, startMs, endMs, durationMs };
}
