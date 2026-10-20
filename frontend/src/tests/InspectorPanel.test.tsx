import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { InspectorPanel } from "../components/studio/inspector/InspectorPanel";
import { EditTabContent } from "../components/studio/inspector/EditTabContent";
import { CaptionsTabContent } from "../components/studio/inspector/CaptionsTabContent";
import { ExportTabContent } from "../components/studio/inspector/ExportTabContent";
import { ClipEditSettings, CaptionStyleOptions, ExportSettings } from "../features/studio/types";

const mockEditSettings: ClipEditSettings = {
  clipName: "Clip #1 - Financial Freedom",
  startSec: 2.15,
  endSec: 32.4,
  aspectRatio: "9:16",
  autoReframe: true,
  motionSmoothing: 75,
  splitScreen: false,
};

const mockCaptionOptions: CaptionStyleOptions = {
  preset: "neon-glow",
  fontFamily: "Cairo",
  fontSize: "lg",
  position: "bottom",
  textColor: "#FFFFFF",
  highlightColor: "#00F2FE",
  karaokeSync: true,
};

const mockExportSettings: ExportSettings = {
  fileName: "Laqta_Clip_01_Short.mp4",
  resolution: "1080p",
  format: "mp4",
  burnInSubtitles: true,
};

describe("InspectorPanel & Sub-Tabs", () => {
  it("renders inspector navigation tabs and displays active edit tab by default", () => {
    render(
      <InspectorPanel
        activeTab="edit"
        onTabChange={vi.fn()}
        editSettings={mockEditSettings}
        onUpdateEditSettings={vi.fn()}
        captionOptions={mockCaptionOptions}
        onUpdateCaptionOptions={vi.fn()}
        exportSettings={mockExportSettings}
        onUpdateExportSettings={vi.fn()}
        onExport={vi.fn()}
      />,
    );

    expect(screen.getByTestId("studio-inspector-panel")).toBeInTheDocument();
    expect(screen.getByTestId("inspector-tab-edit")).toBeInTheDocument();
    expect(screen.getByTestId("inspector-tab-captions")).toBeInTheDocument();
    expect(screen.getByTestId("inspector-tab-export")).toBeInTheDocument();
    expect(screen.getByTestId("edit-tab-content")).toBeInTheDocument();
  });

  it("wires the tabs to their panel for assistive technology", () => {
    render(
      <InspectorPanel
        activeTab="edit"
        onTabChange={vi.fn()}
        editSettings={mockEditSettings}
        onUpdateEditSettings={vi.fn()}
        captionOptions={mockCaptionOptions}
        onUpdateCaptionOptions={vi.fn()}
        exportSettings={mockExportSettings}
        onUpdateExportSettings={vi.fn()}
        onExport={vi.fn()}
      />,
    );

    const editTab = screen.getByTestId("inspector-tab-edit");
    expect(editTab).toHaveAttribute("aria-controls", "inspector-panel-edit");

    // The active tab must point at a real, labelled tabpanel.
    const panel = document.getElementById("inspector-panel-edit");
    expect(panel).toBeInTheDocument();
    expect(panel).toHaveAttribute("role", "tabpanel");
    expect(panel).toHaveAttribute("aria-labelledby", "inspector-tab-edit");
  });

  it("handles tab switching callbacks", async () => {
    const user = userEvent.setup();
    const onTabChange = vi.fn();

    render(
      <InspectorPanel
        activeTab="edit"
        onTabChange={onTabChange}
        editSettings={mockEditSettings}
        onUpdateEditSettings={vi.fn()}
        captionOptions={mockCaptionOptions}
        onUpdateCaptionOptions={vi.fn()}
        exportSettings={mockExportSettings}
        onUpdateExportSettings={vi.fn()}
        onExport={vi.fn()}
      />,
    );

    const captionsTab = screen.getByTestId("inspector-tab-captions");
    await user.click(captionsTab);
    expect(onTabChange).toHaveBeenCalledWith("captions");

    const exportTab = screen.getByTestId("inspector-tab-export");
    await user.click(exportTab);
    expect(onTabChange).toHaveBeenCalledWith("export");
  });

  it("handles edit settings changes in EditTabContent", async () => {
    const user = userEvent.setup();
    const onUpdate = vi.fn();

    render(<EditTabContent settings={mockEditSettings} onUpdateSettings={onUpdate} />);

    // Edit clip name
    const input = screen.getByTestId("clip-name-input");
    await user.clear(input);
    await user.type(input, "Viral Hook #2");
    expect(onUpdate).toHaveBeenCalled();

    // Select aspect ratio tile
    const tile16x9 = screen.getByTestId("ar-tile-16:9");
    await user.click(tile16x9);
    expect(onUpdate).toHaveBeenCalledWith({ aspectRatio: "16:9" });

    // Toggle auto-reframe
    const toggle = screen.getByTestId("auto-reframe-toggle");
    await user.click(toggle);
    expect(onUpdate).toHaveBeenCalledWith({ autoReframe: false });

    // Motion smoothing slider
    const slider = screen.getByTestId("motion-smoothing-slider");
    fireEvent.change(slider, { target: { value: "90" } });
    expect(onUpdate).toHaveBeenCalledWith({ motionSmoothing: 90 });
  });

  it("handles caption style presets and color swatch clicks in CaptionsTabContent", async () => {
    const user = userEvent.setup();
    const onUpdate = vi.fn();

    render(<CaptionsTabContent options={mockCaptionOptions} onUpdateOptions={onUpdate} />);

    // Preset select
    const cyberpunkPreset = screen.getByTestId("preset-btn-cyberpunk");
    await user.click(cyberpunkPreset);
    expect(onUpdate).toHaveBeenCalledWith({
      preset: "cyberpunk",
      highlightColor: "#FACC15",
    });

    // Color swatch click
    const purpleSwatch = screen.getByTestId("color-swatch-neon-purple");
    await user.click(purpleSwatch);
    expect(onUpdate).toHaveBeenCalledWith({ highlightColor: "#A855F7" });

    // Karaoke sync toggle
    const syncToggle = screen.getByTestId("karaoke-sync-toggle");
    await user.click(syncToggle);
    expect(onUpdate).toHaveBeenCalledWith({ karaokeSync: false });
  });

  it("handles export options and Export Short button trigger in ExportTabContent", async () => {
    const user = userEvent.setup();
    const onUpdate = vi.fn();
    const onExport = vi.fn();

    render(
      <ExportTabContent
        settings={mockExportSettings}
        onUpdateSettings={onUpdate}
        onExport={onExport}
      />,
    );

    // Select 4K resolution
    const res4k = screen.getByTestId("res-option-4k");
    await user.click(res4k);
    expect(onUpdate).toHaveBeenCalledWith({ resolution: "4k" });

    // Click Export Short button
    const exportBtn = screen.getByTestId("export-short-btn");
    await user.click(exportBtn);
    expect(onExport).toHaveBeenCalledTimes(1);
  });
});
