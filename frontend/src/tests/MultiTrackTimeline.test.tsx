import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MultiTrackTimeline } from "../components/studio/timeline/MultiTrackTimeline";
import { WaveformTrack } from "../components/studio/timeline/WaveformTrack";
import { SubtitleBlocksTrack } from "../components/studio/timeline/SubtitleBlocksTrack";
import { TranscriptSegment } from "../types/transcription";

const mockSegments: TranscriptSegment[] = [
  {
    id: "seg_1",
    start: 0,
    end: 15,
    text: "Opening hook phrase",
  },
  {
    id: "seg_2",
    start: 15,
    end: 30,
    text: "Punchline key takeaway",
  },
];

describe("MultiTrackTimeline & Tracks", () => {
  it("renders multi-track timeline with ruler, video, audio, and captions tracks", () => {
    render(<MultiTrackTimeline currentTimeSec={18} durationSec={30} onSeek={vi.fn()} />);

    expect(screen.getByTestId("multi-track-timeline")).toBeInTheDocument();
    expect(screen.getByText("Multi-Track Timeline")).toBeInTheDocument();
    expect(screen.getByText("Video")).toBeInTheDocument();
    expect(screen.getByText("Audio")).toBeInTheDocument();
    expect(screen.getByText("Captions")).toBeInTheDocument();

    // Timecode check
    expect(screen.getByText("00:18")).toBeInTheDocument();
    expect(screen.getAllByText("00:30").length).toBeGreaterThanOrEqual(1);

    // All 3 tracks rendered
    expect(screen.getByTestId("filmstrip-track")).toBeInTheDocument();
    expect(screen.getByTestId("waveform-track")).toBeInTheDocument();
    expect(screen.getByTestId("subtitle-blocks-track")).toBeInTheDocument();
  });

  it("handles zoom in and zoom out controls", async () => {
    const user = userEvent.setup();

    render(<MultiTrackTimeline currentTimeSec={0} durationSec={30} onSeek={vi.fn()} />);

    expect(screen.getByText("100%")).toBeInTheDocument();

    const zoomInBtn = screen.getByTestId("zoom-in-btn");
    await user.click(zoomInBtn);
    expect(screen.getByText("125%")).toBeInTheDocument();

    const zoomOutBtn = screen.getByTestId("zoom-out-btn");
    await user.click(zoomOutBtn);
    expect(screen.getByText("100%")).toBeInTheDocument();
  });

  it("positions neon cyan playhead at current timecode and handles seeking on waveform", () => {
    const onSeek = vi.fn();

    render(<WaveformTrack currentTimeSec={15} durationSec={30} onSeek={onSeek} zoom={1} />);

    const playhead = screen.getByTestId("timeline-playhead");
    expect(playhead).toBeInTheDocument();
    expect(playhead.style.left).toBe("50%");

    const track = screen.getByTestId("waveform-track");
    // Mock getBoundingClientRect
    vi.spyOn(track, "getBoundingClientRect").mockReturnValue({
      left: 0,
      top: 0,
      width: 300,
      height: 64,
      right: 300,
      bottom: 64,
      x: 0,
      y: 0,
      toJSON: () => {},
    });

    fireEvent.mouseDown(track, { clientX: 200 });
    // 200 / 300 * 30s = 20s
    expect(onSeek).toHaveBeenCalledWith(20);
  });

  it("renders active clip boundary window on filmstrip track", () => {
    render(
      <MultiTrackTimeline
        currentTimeSec={0}
        durationSec={60}
        onSeek={vi.fn()}
        activeClipWindow={{ startSec: 15, endSec: 45 }}
      />,
    );

    const windowOverlay = screen.getByTestId("active-clip-filmstrip-window");
    expect(windowOverlay).toBeInTheDocument();
    expect(windowOverlay.style.left).toBe("25%"); // 15s / 60s
    expect(windowOverlay.style.width).toBe("50%"); // 30s / 60s
  });

  it("renders subtitle blocks and triggers onSelectSegment callback", async () => {
    const user = userEvent.setup();
    const onSelectSegment = vi.fn();

    render(
      <SubtitleBlocksTrack
        segments={mockSegments}
        durationSec={30}
        zoom={1}
        onSelectSegment={onSelectSegment}
      />,
    );

    expect(screen.getByText("Opening hook phrase")).toBeInTheDocument();
    expect(screen.getByText("Punchline key takeaway")).toBeInTheDocument();

    const block1 = screen.getByTestId("subtitle-block-seg_1");
    await user.click(block1);
    expect(onSelectSegment).toHaveBeenCalledWith(mockSegments[0]);
  });
});
