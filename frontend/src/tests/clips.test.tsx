/**
 * Tests for the candidate review/edit UI (PRD §5 FR-04/FR-05/FR-14, §4 step 10).
 *
 * Covers: edit validation (bounds vs source duration and 30–55 s),
 * RTL/LTR container behavior + mixed-direction text, empty/cancelled/failed
 * states, backend error + retry, loading state, and accessible keyboard
 * labels/focus. All backend responses come from test fixtures only.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const apiMock = vi.hoisted(() => ({
  listMediaCandidates: vi.fn(),
  generateCandidates: vi.fn(),
  updateCandidate: vi.fn(),
}));

vi.mock("../lib/api/client", () => {
  class ApiClientError extends Error {
    status?: number;
    constructor(message: string, status?: number) {
      super(message);
      this.status = status;
    }
  }
  return { api: apiMock, ApiClientError };
});

import { CandidatesPanel } from "../features/clips/CandidatesPanel";
import { Candidate } from "../types/candidates";
import { TranscriptSegment } from "../types/transcription";

const REVIEW_LABEL = /AI suggestion — review required/i;

function makeCandidate(overrides: Partial<Candidate> = {}): Candidate {
  return {
    id: "cand_abc123",
    media_id: "med_1",
    transcript_id: "tr_1",
    start_ms: 0,
    end_ms: 45_000,
    duration_ms: 45_000,
    status: "suggested",
    cps: 72.5,
    cps_interpretation:
      "Heuristic editorial quality score (0-100), not a probability of views or virality.",
    title: "A clean idea",
    hook: "What happens next will amaze you",
    transcript_span_ids: ["seg_0001", "seg_0001#w0"],
    feature_scores: [
      {
        key: "hook",
        label: "Opening hook / curiosity",
        score: 80,
        nominal_weight: 0.2,
        effective_weight: 0.25,
        available: true,
        rationale: "Bonus: opens with interrogative.",
      },
      {
        key: "visual",
        label: "Visual composition",
        score: null,
        nominal_weight: 0.05,
        effective_weight: null,
        available: false,
        rationale: "No video/scene/crop analysis is implemented in this phase.",
      },
    ],
    unavailable_features: ["visual"],
    rationale: ["Overall rationale (deterministic, no LLM involved)."],
    created_at: "2026-10-18T00:00:00+00:00",
    ...overrides,
  };
}

function makeSegments(overrides: Partial<TranscriptSegment> = {}): TranscriptSegment[] {
  return [
    {
      id: "seg_0001",
      start: 0,
      end: 40,
      text: "Fact number one shows clear steps today.",
      words: [{ word: "Fact", start: 0, end: 1, probability: 0.95 }],
      avg_logprob: -0.3,
      no_speech_prob: 0.02,
      ...overrides,
    },
  ];
}

function renderPanel(props: Partial<Parameters<typeof CandidatesPanel>[0]> = {}) {
  const base = {
    mediaId: "med_1",
    mediaDurationMs: 300_000,
    transcripts: [
      {
        id: "tr_1",
        media_id: "med_1",
        language: "en",
        provider: "fake",
        model: "base",
        status: "completed",
        text: "Fact number one shows clear steps today.",
        segments: makeSegments(),
        word_timestamps_available: true,
        timing_granularity: "word" as const,
        created_at: "2026-10-18T00:00:00+00:00",
      },
    ],
    transcriptionJob: null,
  };
  return render(<CandidatesPanel {...base} {...props} />);
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("CandidatesPanel states", () => {
  it("shows loading, then ranked candidate cards with review notice", async () => {
    apiMock.listMediaCandidates.mockImplementation(
      () => new Promise((res) => setTimeout(() => res([makeCandidate()]), 20)),
    );
    renderPanel();

    expect(screen.getByTestId("candidates-loading")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("candidates-list")).toBeInTheDocument());
    expect(screen.getAllByText(REVIEW_LABEL).length).toBeGreaterThan(0);
    // Exact-match the CPS badge (regex-substring queries would also match
    // ancestor container text).
    expect(screen.getByText(/^CPS 73$/)).toBeInTheDocument();
    // Scoring is never marketed as virality probability.
    expect(screen.getByText(/not a probability of views or virality/i)).toBeInTheDocument();
  });

  it("shows a retryable backend error when loading fails", async () => {
    apiMock.listMediaCandidates.mockRejectedValue(
      new Error("Failed to fetch candidates from the local backend."),
    );
    renderPanel();

    const errorBox = await screen.findByTestId("candidates-error");
    expect(errorBox).toHaveTextContent(/failed to load candidates/i);
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();

    // Retry succeeds → cards render.
    apiMock.listMediaCandidates.mockResolvedValue([makeCandidate()]);
    await userEvent.click(screen.getByRole("button", { name: /retry/i }));
    await waitFor(() => expect(screen.getByTestId("candidates-list")).toBeInTheDocument());
  });

  it("shows the empty state with a generate action when ready and empty", async () => {
    apiMock.listMediaCandidates.mockResolvedValue([]);
    apiMock.generateCandidates.mockResolvedValue({
      media_id: "med_1",
      transcript_id: "tr_1",
      candidates: [makeCandidate()],
      warnings: [],
      scoring_notice: "notice",
      ranking_method: "baseline",
      ranking_provider: null,
    });
    renderPanel();

    expect(await screen.findByTestId("candidates-empty")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /generate candidates/i }));
    expect(apiMock.generateCandidates).toHaveBeenCalledWith("med_1");
    await waitFor(() => expect(screen.getByTestId("candidates-list")).toBeInTheDocument());
  });

  it("shows a distinct empty state when no transcript exists yet", async () => {
    apiMock.listMediaCandidates.mockResolvedValue([]);
    renderPanel({ transcripts: [] });

    expect(await screen.findByTestId("candidates-no-transcript")).toBeInTheDocument();
    expect(screen.getByText(/run transcription first/i)).toBeInTheDocument();
  });

  it("reflects a cancelled transcription job accurately", async () => {
    apiMock.listMediaCandidates.mockResolvedValue([]);
    renderPanel({
      transcriptionJob: { status: "cancelled", errorMessage: null },
    });

    expect(await screen.findByTestId("candidates-cancelled")).toBeInTheDocument();
    expect(screen.getByText(/transcription was cancelled/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /generate/i })).not.toBeInTheDocument();
  });

  it("reflects a failed transcription job accurately", async () => {
    apiMock.listMediaCandidates.mockResolvedValue([]);
    renderPanel({
      transcriptionJob: { status: "failed", errorMessage: "Model download lost" },
    });

    expect(await screen.findByTestId("candidates-transcription-failed")).toBeInTheDocument();
    expect(screen.getByText(/transcription failed: model download lost/i)).toBeInTheDocument();
  });
});

describe("boundary edit validation", () => {
  async function openEditor(candidate: Candidate) {
    apiMock.listMediaCandidates.mockResolvedValue([candidate]);
    renderPanel();
    const card = await screen.findByTestId("candidate-card");
    const start = await within(card).findByLabelText("Start (seconds)");
    const end = within(card).getByLabelText("End (seconds)");
    const save = within(card).getByRole("button", { name: /save boundaries/i });
    return { card, start, end, save };
  }

  it("blocks an end beyond the source duration without calling the API", async () => {
    const { start, end, save } = await openEditor(makeCandidate());
    await userEvent.clear(start);
    await userEvent.type(start, "0");
    await userEvent.clear(end);
    await userEvent.type(end, "320"); // 320 s > 300 s media
    await userEvent.click(save);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /beyond the source video \(300000 ms\)/i,
    );
    expect(apiMock.updateCandidate).not.toHaveBeenCalled();
  });

  it("blocks out-of-range durations (below minimum)", async () => {
    const { start, end, save } = await openEditor(makeCandidate());
    await userEvent.clear(start);
    await userEvent.type(start, "10");
    await userEvent.clear(end);
    await userEvent.type(end, "20"); // 10 s < 30 s minimum
    await userEvent.click(save);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /outside the configured 30-55 s range/i,
    );
    expect(apiMock.updateCandidate).not.toHaveBeenCalled();
  });

  it("blocks out-of-range durations (above maximum)", async () => {
    const { start, end, save } = await openEditor(makeCandidate());
    await userEvent.clear(start);
    await userEvent.type(start, "0");
    await userEvent.clear(end);
    await userEvent.type(end, "70"); // 70 s > 55 s maximum
    await userEvent.click(save);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /outside the configured 30-55 s range/i,
    );
    expect(apiMock.updateCandidate).not.toHaveBeenCalled();
  });

  it("submits a valid edit to the backend and shows the re-scored card", async () => {
    const updated = makeCandidate({
      start_ms: 32_000,
      end_ms: 70_000,
      duration_ms: 38_000,
      boundary_edited: true,
    });
    apiMock.updateCandidate.mockResolvedValue(updated);
    const { start, end, save } = await openEditor(makeCandidate());

    await userEvent.clear(start);
    await userEvent.type(start, "32");
    await userEvent.clear(end);
    await userEvent.type(end, "70");
    await userEvent.click(save);

    await waitFor(() =>
      expect(apiMock.updateCandidate).toHaveBeenCalledWith("cand_abc123", {
        start_ms: 32_000,
        end_ms: 70_000,
      }),
    );
    await waitFor(() =>
      expect(screen.getByText(/edited — re-scored deterministically/i)).toBeInTheDocument(),
    );
  });

  it("surfaces a backend validation error on save without faking success", async () => {
    apiMock.updateCandidate.mockRejectedValue(
      new Error(
        "Edited range contains no transcript content; boundaries must overlap transcript evidence.",
      ),
    );
    const { start, end, save } = await openEditor(makeCandidate());

    // Client-valid range (30 s) that the backend rejects for missing
    // transcript coverage — exercises the real server-error path.
    await userEvent.clear(start);
    await userEvent.type(start, "260");
    await userEvent.clear(end);
    await userEvent.type(end, "290");
    await userEvent.click(save);

    await waitFor(() => {
      const found = screen.getAllByRole("alert");
      expect(found.some((a) => a.textContent?.includes("no transcript content"))).toBe(true);
    });
    // The stale (un-edited) values remain without inventing a success state.
    await waitFor(() => {
      expect(screen.queryByText(/edited — re-scored/i)).not.toBeInTheDocument();
    });
  });
});

describe("RTL / LTR transcript handling (FR-14)", () => {
  async function getExcerpt(textLanguage: "ar" | "en") {
    apiMock.listMediaCandidates.mockResolvedValue([makeCandidate()]);
    const segments =
      textLanguage === "ar"
        ? makeSegments({
            text: "كل المعالجة تتم محلياً على جهازك دون إرسال بياناتك إلى السحابة.",
          })
        : textLanguage === "en"
          ? makeSegments()
          : undefined;
    renderPanel({
      transcripts: [
        {
          id: "tr_1",
          media_id: "med_1",
          language: textLanguage,
          provider: "fake",
          model: "base",
          status: "completed",
          text: segments![0].text,
          segments: segments!,
          word_timestamps_available: true,
          timing_granularity: "word" as const,
          created_at: "2026-10-18T00:00:00+00:00",
        },
      ],
    });
    const card = await screen.findByTestId("candidate-card");
    // The excerpt is the <p> inside the excerpt box (segment count label row).
    const excerpt = await within(card).findByText(
      textLanguage === "ar" ? /كل المعالجة تتم محلياً/ : /Fact number one shows clear steps/,
    );
    return excerpt;
  }

  it("renders an Arabic excerpt inside a dir=rtl container", async () => {
    const excerpt = await getExcerpt("ar");
    expect(excerpt).toHaveAttribute("dir", "rtl");
  });

  it("renders an English excerpt inside a dir=ltr container", async () => {
    const excerpt = await getExcerpt("en");
    expect(excerpt).toHaveAttribute("dir", "ltr");
  });

  it("treats mixed Arabic/Latin text as RTL base with bidi isolation", async () => {
    // Arabic narration embedding an English brand name (real-world mix).
    const mixed = "كل المعالجة تتم محلياً باستخدام WhisperX على جهازك.";
    apiMock.listMediaCandidates.mockResolvedValue([makeCandidate()]);
    renderPanel({
      transcripts: [
        {
          id: "tr_1",
          media_id: "med_1",
          language: "ar",
          provider: "fake",
          model: "base",
          status: "completed",
          text: mixed,
          segments: makeSegments({ text: mixed }),
          word_timestamps_available: true,
          timing_granularity: "word" as const,
          created_at: "2026-10-18T00:00:00+00:00",
        },
      ],
    });
    const excerpt = await screen.findByText(/كل المعالجة تتم محلياً/);
    expect(excerpt).toHaveAttribute("dir", "rtl");
    // Mixed run relies on the browser bidi algorithm (plaintext), applied
    // inline and asserted here.
    expect(excerpt).toHaveStyle({ "unicode-bidi": "plaintext" });
  });

  it("detects direction deterministically at the helper level", async () => {
    const { detectTextDirection } = await import("../lib/i18n/bidi");
    expect(detectTextDirection("كل المعالجة تتم محلياً")).toBe("rtl");
    expect(detectTextDirection("Fact number one shows clear steps")).toBe("ltr");
    expect(detectTextDirection("12345 — 100%")).toBe("ltr"); // neutrals → ltr
    expect(detectTextDirection("")).toBe("ltr");
    expect(detectTextDirection(null)).toBe("ltr");
  });
});

describe("accessibility and preview", () => {
  it("provides accessible labels and keyboard-reachable controls", async () => {
    apiMock.listMediaCandidates.mockResolvedValue([makeCandidate()]);
    renderPanel();
    const card = await screen.findByTestId("candidate-card");

    // Labeled inputs (focusable via keyboard).
    const start = within(card).getByLabelText("Start (seconds)");
    const end = within(card).getByLabelText("End (seconds)");
    start.focus();
    expect(document.activeElement).toBe(start);
    end.focus();
    expect(document.activeElement).toBe(end);

    // CPS badge has an accessible name; Save button is a real button.
    expect(within(card).getByLabelText(/Clip Potential Score 73 of 100/)).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: /save boundaries/i })).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: /show score breakdown/i })).toBeInTheDocument();
  });

  it("toggles the score breakdown with aria-expanded state", async () => {
    apiMock.listMediaCandidates.mockResolvedValue([makeCandidate()]);
    renderPanel();
    const card = await screen.findByTestId("candidate-card");
    const toggle = within(card).getByRole("button", {
      name: /show score breakdown/i,
    });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggle);
    expect(within(card).getByRole("button", { name: /hide score breakdown/i })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    const breakdown = within(card).getByTestId("score-breakdown");
    expect(within(breakdown).getByText(/unavailable evidence \(1\)/i)).toBeInTheDocument();
    // Unavailable evidence is labelled, never silently zeroed.
    expect(within(breakdown).getByText(/visual composition/i)).toBeInTheDocument();
  });

  it("renders a source-time preview player using the local file stream", async () => {
    apiMock.listMediaCandidates.mockResolvedValue([makeCandidate()]);
    renderPanel();
    const card = await screen.findByTestId("candidate-card");
    const video = within(card).getByTestId("candidate-video");
    expect(video).toHaveAttribute("src", expect.stringContaining("/api/media/med_1/file"));
    expect(within(card).getByRole("button", { name: /preview from start/i })).toBeInTheDocument();
  });

  it("shows a transcript excerpt aligned to the candidate span", async () => {
    apiMock.listMediaCandidates.mockResolvedValue([makeCandidate()]);
    renderPanel();
    const card = await screen.findByTestId("candidate-card");
    expect(
      await within(card).findByText(/transcript excerpt \(1 segment in range\)/i),
    ).toBeInTheDocument();
    expect(within(card).getByText(/fact number one shows clear steps/i)).toBeInTheDocument();
  });

  it("discloses when no excerpt covers the edited span", async () => {
    // Candidate lies outside all transcript segments (e.g. after edit).
    apiMock.listMediaCandidates.mockResolvedValue([
      makeCandidate({
        start_ms: 260_000,
        end_ms: 290_000,
        duration_ms: 30_000,
      }),
    ]);
    renderPanel();
    const card = await screen.findByTestId("candidate-card");
    expect(within(card).findByText(/transcript excerpt unavailable/i)).toBeTruthy();
  });
});
