import { Candidate } from "../types/candidates";

/**
 * Picks the first rationale line that actually carries information.
 *
 * The backend emits an "Overall rationale (deterministic, no LLM involved):"
 * header followed by one line per scored feature. Showing the header alone
 * leaves the card with an empty line, so the header is skipped and the first
 * substantive explanation is used instead.
 */
export function pickMeaningfulRationale(candidate: Candidate): string | null {
  const lines = (candidate.rationale ?? []).filter((line) => line && line.trim().length > 0);
  const substantive = lines.find((line) => !/^overall rationale/i.test(line.trim()));
  if (substantive) return substantive.trim();
  return lines[0]?.trim() ?? null;
}
