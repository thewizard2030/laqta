import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { VideoImportHero } from "../components/studio/VideoImportHero";

describe("VideoImportHero Component", () => {
  it("renders upload button, youtube link button, and 100% local processing notice", () => {
    render(<VideoImportHero onUploadFile={vi.fn()} />);

    expect(screen.getByText(/Import Your Video/i)).toBeInTheDocument();
    expect(screen.getByText(/100% Local Processing/i)).toBeInTheDocument();
    expect(screen.getByTestId("import-upload-btn")).toBeInTheDocument();
    expect(screen.getByTestId("import-youtube-btn")).toBeInTheDocument();
  });

  it("handles file selection via hidden file input", async () => {
    const user = userEvent.setup();
    const onUpload = vi.fn().mockResolvedValue(undefined);

    render(<VideoImportHero onUploadFile={onUpload} />);

    const fileInput = screen.getByTestId("hero-file-input");
    const file = new File(["test-content"], "podcast.mp4", { type: "video/mp4" });
    await user.upload(fileInput, file);

    expect(onUpload).toHaveBeenCalledWith(file);
  });

  it("opens YouTube modal and validates video URL input", async () => {
    const user = userEvent.setup();
    const onYouTubeUrl = vi.fn().mockResolvedValue(undefined);

    render(<VideoImportHero onUploadFile={vi.fn()} onYouTubeUrl={onYouTubeUrl} />);

    const ytBtn = screen.getByTestId("import-youtube-btn");
    await user.click(ytBtn);

    expect(screen.getByTestId("youtube-import-modal")).toBeInTheDocument();
    expect(screen.getByText(/Local-First Download/i)).toBeInTheDocument();

    const submitBtn = screen.getByTestId("youtube-submit-btn");
    await user.click(submitBtn);

    expect(screen.getByText(/Please enter a valid video link/i)).toBeInTheDocument();

    const urlInput = screen.getByTestId("youtube-url-input");
    await user.type(urlInput, "https://www.youtube.com/watch?v=dQw4w9WgXcQ");
    await user.click(submitBtn);

    expect(onYouTubeUrl).toHaveBeenCalledWith("https://www.youtube.com/watch?v=dQw4w9WgXcQ");
  });

  it("displays active media summary when media is already imported", () => {
    render(
      <VideoImportHero
        onUploadFile={vi.fn()}
        activeMedia={{
          original_name: "interview_full.mp4",
          duration_ms: 65000,
          width: 1920,
          height: 1080,
          video_codec: "h264",
        }}
      />,
    );

    expect(screen.getByText("interview_full.mp4")).toBeInTheDocument();
    expect(screen.getByText(/1920×1080/i)).toBeInTheDocument();
    expect(screen.getByText(/h264/i)).toBeInTheDocument();
    expect(screen.getByTestId("replace-media-btn")).toBeInTheDocument();
  });
});
