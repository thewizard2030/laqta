import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SuggestedClipsList } from "../components/studio/clips/SuggestedClipsList";
import { Candidate } from "../types/candidates";

const mockCandidates: Candidate[] = [
  {
    id: "cand_1",
    media_id: "med_1",
    transcript_id: "tr_1",
    start_ms: 10000,
    end_ms: 40000,
    duration_ms: 30000,
    status: "suggested",
    cps: 96,
    cps_interpretation: "Top viral potential",
    title: "The Financial Freedom Rule",
    hook: "القاعدة الوحيدة للحرية المالية",
    transcript_span_ids: [],
    feature_scores: [],
    unavailable_features: [],
    rationale: ["High engagement opening"],
    created_at: "2026-10-18T05:00:00Z",
  },
  {
    id: "cand_2",
    media_id: "med_1",
    transcript_id: "tr_1",
    start_ms: 50000,
    end_ms: 85000,
    duration_ms: 35000,
    status: "suggested",
    cps: 88,
    cps_interpretation: "Strong retention hook",
    title: "Audience Growth Secrets",
    hook: "How to Build an Audience Fast",
    transcript_span_ids: [],
    feature_scores: [],
    unavailable_features: [],
    rationale: ["Clear educational takeaway"],
    created_at: "2026-10-18T05:00:00Z",
  },
];

describe("SuggestedClipsList Component", () => {
  it("renders ranked list of clips with score badges, hooks, and tags", () => {
    render(
      <SuggestedClipsList
        candidates={mockCandidates}
        selectedCandidateId="cand_1"
        onSelectCandidate={vi.fn()}
      />,
    );

    expect(screen.getByText(/AI Suggested Clips/i)).toBeInTheDocument();
    expect(screen.getByText(/2 clips/i)).toBeInTheDocument();

    // Verify ranks and scores
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("96")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("88")).toBeInTheDocument();

    // Verify hooks rendered
    expect(screen.getByText(/القاعدة الوحيدة للحرية المالية/i)).toBeInTheDocument();
    expect(screen.getByText(/How to Build an Audience Fast/i)).toBeInTheDocument();
  });

  it("highlights the selected candidate with the brand accent and triggers callback on click", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();

    render(
      <SuggestedClipsList
        candidates={mockCandidates}
        selectedCandidateId="cand_1"
        onSelectCandidate={onSelect}
      />,
    );

    const card1 = screen.getByTestId("clip-card-cand_1");
    expect(card1.className).toContain("border-laqta-500/70");

    const card2 = screen.getByTestId("clip-card-cand_2");
    await user.click(card2);

    expect(onSelect).toHaveBeenCalledWith(mockCandidates[1]);
  });

  it("handles sorting toggle and tag filtering", async () => {
    const user = userEvent.setup();

    render(
      <SuggestedClipsList
        candidates={mockCandidates}
        selectedCandidateId={null}
        onSelectCandidate={vi.fn()}
      />,
    );

    const sortBtn = screen.getByTestId("sort-toggle-btn");
    await user.click(sortBtn); // Switch from score to time
    expect(screen.getByText(/Time/i)).toBeInTheDocument();

    const hookFilter = screen.getByRole("button", { name: /Trending Hooks/i });
    await user.click(hookFilter);

    // Cand 1 has cps 96 (hook), Cand 2 has cps 88
    expect(screen.getByText("96")).toBeInTheDocument();
  });

  it("displays empty state when no candidates exist and triggers generate callback", async () => {
    const user = userEvent.setup();
    const onGenerate = vi.fn();

    render(
      <SuggestedClipsList
        candidates={[]}
        selectedCandidateId={null}
        onSelectCandidate={vi.fn()}
        onGenerateCandidates={onGenerate}
      />,
    );

    expect(screen.getByText(/No AI clips generated yet/i)).toBeInTheDocument();
    const genBtn = screen.getByTestId("generate-clips-btn");
    await user.click(genBtn);

    expect(onGenerate).toHaveBeenCalledTimes(1);
  });

  it("requests a real preview frame when a media id is provided", () => {
    render(
      <SuggestedClipsList
        candidates={mockCandidates}
        selectedCandidateId={null}
        onSelectCandidate={vi.fn()}
        mediaId="med_1"
      />,
    );

    // Frames are served by the `candidate_thumbnails` background job; the
    // card must point at the real endpoint (not a fake screenshot) and fall
    // back to the placeholder via onError if the frame is not ready (404).
    const img = screen.getByTestId("clip-thumbnail-" + mockCandidates[0].id) as HTMLImageElement;
    expect(img.src).toContain(
      `/api/media/med_1/candidates/${encodeURIComponent(mockCandidates[0].id)}/thumbnail`,
    );

    fireEvent.error(img);
    // After the error the card degrades to the honest placeholder (no img).
    expect(screen.queryByTestId("clip-thumbnail-" + mockCandidates[0].id)).not.toBeInTheDocument();
  });

  it("shows the first meaningful rationale line, not the empty header", () => {
    const candidate: Candidate = {
      ...mockCandidates[0],
      rationale: [
        "Overall rationale (deterministic, no LLM involved):",
        "Boundary/timing quality: Duration 37.0s vs target 42.5s (fit 78/100).",
      ],
    };

    render(
      <SuggestedClipsList
        candidates={[candidate]}
        selectedCandidateId={null}
        onSelectCandidate={vi.fn()}
      />,
    );

    // The header alone would leave the card with an empty line.
    expect(screen.getByText(/Boundary\/timing quality: Duration 37.0s/)).toBeInTheDocument();
    expect(screen.queryByText(/Overall rationale \(deterministic/)).not.toBeInTheDocument();
  });

  it("mounts the first page of clips and reveals the rest on demand", async () => {
    const user = userEvent.setup();
    const many: Candidate[] = Array.from({ length: 45 }, (_, i) => ({
      ...mockCandidates[0],
      id: `cand_${i}`,
      title: `Clip ${i}`,
    }));

    render(
      <SuggestedClipsList
        candidates={many}
        selectedCandidateId={null}
        onSelectCandidate={vi.fn()}
      />,
    );

    // Only the first page is mounted — 84 cards must not hit the DOM at once.
    expect(screen.getByTestId("clip-card-cand_0")).toBeInTheDocument();
    expect(screen.queryByTestId("clip-card-cand_30")).not.toBeInTheDocument();

    const showMore = screen.getByTestId("show-more-clips-btn");
    expect(showMore).toHaveTextContent("25 remaining");

    await user.click(showMore);
    expect(screen.getByTestId("clip-card-cand_30")).toBeInTheDocument();
  });
});
