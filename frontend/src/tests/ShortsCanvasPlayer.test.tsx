import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ShortsCanvasPlayer } from "../components/studio/canvas/ShortsCanvasPlayer";
import { LiveKaraokeCaption } from "../components/studio/canvas/LiveKaraokeCaption";
import { PlayerControlsBar } from "../components/studio/canvas/PlayerControlsBar";
import { TranscriptSegment } from "../types/transcription";

const mockSegmentsWithWords: TranscriptSegment[] = [
  {
    id: "seg_1",
    start: 0,
    end: 5,
    text: "القاعدة الوحيدة للحرية المالية",
    words: [
      { word: "القاعدة", start: 0, end: 1.5 },
      { word: "الوحيدة", start: 1.5, end: 3.0 },
      { word: "للحرية", start: 3.0, end: 4.0 },
      { word: "المالية", start: 4.0, end: 5.0 },
    ],
  },
];

describe("ShortsCanvasPlayer & Live Karaoke Captions", () => {
  it("renders 9:16 phone frame, watermark, aspect ratio toggles, and controls", () => {
    render(
      <ShortsCanvasPlayer
        aspectRatio="9:16"
        onChangeAspectRatio={vi.fn()}
        currentTimeSec={10}
        durationSec={30}
        isPlaying={false}
        onTogglePlay={vi.fn()}
        onSeek={vi.fn()}
      />,
    );

    expect(screen.getByTestId("shorts-canvas-player")).toBeInTheDocument();
    expect(screen.getByTestId("canvas-phone-frame")).toBeInTheDocument();
    expect(screen.getByText("Laqta")).toBeInTheDocument();
    expect(screen.getByTestId("ar-9-16-btn")).toBeInTheDocument();
    expect(screen.getByTestId("ar-1-1-btn")).toBeInTheDocument();
    expect(screen.getByTestId("ar-16-9-btn")).toBeInTheDocument();
    expect(screen.getByTestId("play-pause-btn")).toBeInTheDocument();
  });

  it("handles aspect ratio switching and speaker guide toggle", async () => {
    const user = userEvent.setup();
    const onChangeAr = vi.fn();
    const onToggleGuide = vi.fn();

    render(
      <ShortsCanvasPlayer
        aspectRatio="9:16"
        onChangeAspectRatio={onChangeAr}
        showSpeakerGuide={true}
        onToggleSpeakerGuide={onToggleGuide}
        currentTimeSec={0}
        durationSec={30}
        isPlaying={false}
        onTogglePlay={vi.fn()}
        onSeek={vi.fn()}
      />,
    );

    const btn16x9 = screen.getByTestId("ar-16-9-btn");
    await user.click(btn16x9);
    expect(onChangeAr).toHaveBeenCalledWith("16:9");

    const guideToggle = screen.getByTestId("speaker-guide-toggle-btn");
    await user.click(guideToggle);
    expect(onToggleGuide).toHaveBeenCalledTimes(1);
  });

  it("scrubs time and toggles play/pause in PlayerControlsBar", async () => {
    const user = userEvent.setup();
    const onTogglePlay = vi.fn();
    const onSeek = vi.fn();

    render(
      <PlayerControlsBar
        isPlaying={false}
        onTogglePlay={onTogglePlay}
        currentTimeSec={18}
        durationSec={30}
        onSeek={onSeek}
      />,
    );

    // Formatted time display
    expect(screen.getByText("00:18")).toBeInTheDocument();
    expect(screen.getByText("00:30")).toBeInTheDocument();

    // Click play
    const playBtn = screen.getByTestId("play-pause-btn");
    await user.click(playBtn);
    expect(onTogglePlay).toHaveBeenCalledTimes(1);

    // Scrub slider
    const slider = screen.getByTestId("player-time-slider");
    fireEvent.change(slider, { target: { value: "24" } });
    expect(onSeek).toHaveBeenCalledWith(24);
  });

  it("renders live word-by-word karaoke highlights when words timestamps exist", () => {
    render(<LiveKaraokeCaption currentTimeSec={3.5} segments={mockSegmentsWithWords} />);

    // At 3.5s, "للحرية" is the active word
    const activeWord = screen.getByTestId("karaoke-active-word");
    expect(activeWord).toBeInTheDocument();
    expect(activeWord).toHaveTextContent("للحرية");
  });

  it("renders punchline neon highlight pill when fallback text or segment without words is used", () => {
    render(
      <LiveKaraokeCaption currentTimeSec={2.0} fallbackText="القاعدة الوحيدة للحرية المالية" />,
    );

    const highlightedPhrase = screen.getByTestId("karaoke-highlighted-phrase");
    expect(highlightedPhrase).toBeInTheDocument();
    expect(highlightedPhrase).toHaveTextContent("للحرية المالية");
  });
});
