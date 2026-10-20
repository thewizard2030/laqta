import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TranscriptViewer } from "../features/transcription/TranscriptViewer";
import { api } from "../lib/api/client";
import { TranscriptResponse } from "../types/transcription";

const mockTranscripts: TranscriptResponse[] = [
  {
    id: "tx_run_02",
    media_id: "med_video_01",
    language: "ar",
    provider: "faster-whisper",
    model: "tiny",
    status: "completed",
    text: "أهلاً بكم في بودكاست قطة للتقنية وتطوير البرمجيات.",
    segments: [
      {
        id: "seg_0001",
        start: 0.0,
        end: 4.5,
        text: "أهلاً بكم في بودكاست قطة للتقنية وتطوير البرمجيات.",
        words: null,
      },
    ],
    word_timestamps_available: false,
    timing_granularity: "segment",
    created_at: "2026-10-18T05:30:00Z",
  },
  {
    id: "tx_run_01",
    media_id: "med_video_01",
    language: "en",
    provider: "faster-whisper",
    model: "base",
    status: "completed",
    text: "Welcome to Laqta video editing workflow.",
    segments: [
      {
        id: "seg_0001",
        start: 0.0,
        end: 3.5,
        text: "Welcome to Laqta video editing workflow.",
        words: [
          { word: "Welcome", start: 0.0, end: 0.8, probability: 0.95 },
          { word: "to", start: 0.8, end: 1.0, probability: 0.98 },
          { word: "Laqta", start: 1.0, end: 1.8, probability: 0.92 },
        ],
      },
    ],
    word_timestamps_available: true,
    timing_granularity: "word",
    created_at: "2026-10-18T05:00:00Z",
  },
];

describe("TranscriptViewer Component", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders empty state when no transcripts exist", () => {
    render(
      <TranscriptViewer
        mediaId="med_video_01"
        transcripts={[]}
        isLoading={false}
        isTranscribing={false}
        onStartTranscription={vi.fn()}
        onRefreshTranscripts={vi.fn()}
      />,
    );

    expect(screen.getByText(/no transcripts yet/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /transcribe video/i })).toBeInTheDocument();
  });

  it("opens configuration form and triggers onStartTranscription", async () => {
    const mockStart = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();

    render(
      <TranscriptViewer
        mediaId="med_video_01"
        transcripts={[]}
        isLoading={false}
        isTranscribing={false}
        onStartTranscription={mockStart}
        onRefreshTranscripts={vi.fn()}
      />,
    );

    // Click Transcribe Video to open form
    await user.click(screen.getByRole("button", { name: /transcribe video/i }));

    expect(screen.getByText(/configure speech recognition/i)).toBeInTheDocument();

    // Custom path first: expose manual controls and select 'small' with words
    await user.selectOptions(screen.getByTestId("profile-select"), "custom");
    expect(screen.getByLabelText(/whisper model size/i)).toBeInTheDocument();

    // Select 'small' model
    await user.selectOptions(screen.getByLabelText(/whisper model size/i), "small");

    // Submit form
    await user.click(screen.getByRole("button", { name: /start transcription/i }));

    expect(mockStart).toHaveBeenCalledTimes(1);
    expect(mockStart).toHaveBeenCalledWith(
      expect.objectContaining({
        model_size: "small",
        word_timestamps: true,
      }),
    );

    // Default profile path (reopen the form): choose profile=fast and
    // submit — NO model/word-timestamp override; the backend profile decides.
    mockStart.mockClear();
    await user.click(screen.getByRole("button", { name: /transcribe video/i }));
    expect(screen.getByTestId("profile-select")).toBeInTheDocument();
    await user.selectOptions(screen.getByTestId("profile-select"), "fast");
    await user.click(screen.getByRole("button", { name: /start transcription/i }));

    expect(mockStart).toHaveBeenCalledTimes(1);
    expect(mockStart).toHaveBeenCalledWith(
      expect.objectContaining({
        profile: "fast",
        language: undefined,
      }),
    );
    const payload1 = mockStart.mock.calls[0][0];
    expect(payload1.model_size).toBeUndefined();
    expect(payload1.word_timestamps).toBeUndefined();
  });

  it("truthfully renders granularity badges and switches between runs", async () => {
    const user = userEvent.setup();

    render(
      <TranscriptViewer
        mediaId="med_video_01"
        transcripts={mockTranscripts}
        isLoading={false}
        isTranscribing={false}
        onStartTranscription={vi.fn()}
        onRefreshTranscripts={vi.fn()}
      />,
    );

    // Initial run is run 0 (Arabic, segment-level)
    expect(screen.getByText(/segment-level timings/i)).toBeInTheDocument();
    expect(screen.getByText("AR")).toBeInTheDocument();
    expect(screen.getByText("tiny")).toBeInTheDocument();
    expect(
      screen.getByText("أهلاً بكم في بودكاست قطة للتقنية وتطوير البرمجيات."),
    ).toBeInTheDocument();

    // Switch to English run (word-level)
    const runSelector = screen.getByRole("combobox");
    await user.selectOptions(runSelector, "1");

    // English run should truthfully display word-level timings
    expect(screen.getByText(/word-level timings/i)).toBeInTheDocument();
    expect(screen.getByText("EN")).toBeInTheDocument();
    expect(screen.getByText("base")).toBeInTheDocument();
    expect(screen.getByText("Welcome to Laqta video editing workflow.")).toBeInTheDocument();

    // Word timestamp toggle
    const toggleWordsBtn = screen.getByTitle(/toggle word timestamps/i);
    expect(toggleWordsBtn).toBeInTheDocument();
    await user.click(toggleWordsBtn);

    // Words should be visible
    expect(screen.getByText("Welcome")).toBeInTheDocument();
    expect(screen.getByText("Laqta")).toBeInTheDocument();
  });
});

describe("ApiClient Transcription Methods", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("calls POST /api/media/{mediaId}/transcription-jobs", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({
        id: "job_tx_01",
        project_id: "p1",
        media_id: "m1",
        type: "transcription",
        status: "queued",
        stage: "extracting_audio",
        progress: 0.0,
      }),
    });
    vi.stubGlobal("fetch", mockFetch);

    const job = await api.createTranscriptionJob("m1", {
      model_size: "base",
      language: "en",
    });

    expect(job.id).toBe("job_tx_01");
    expect(job.type).toBe("transcription");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/media/m1/transcription-jobs"),
      expect.objectContaining({
        method: "POST",
      }),
    );
  });

  it("calls GET /api/media/{mediaId}/transcripts", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockTranscripts,
    });
    vi.stubGlobal("fetch", mockFetch);

    const results = await api.listMediaTranscripts("m1");
    expect(results).toHaveLength(2);
    expect(results[0].language).toBe("ar");
    expect(results[1].language).toBe("en");
  });
});
