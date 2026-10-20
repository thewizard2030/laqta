/**
 * Types for Neon AI Shorts Studio workbench & inspector panels.
 */

export type AspectRatioMode = "9:16" | "16:9" | "1:1";
export type InspectorTab = "edit" | "captions" | "export";
export type CaptionPreset = "neon-glow" | "minimalist" | "bold-outline" | "cyberpunk";

export interface CaptionStyleOptions {
  preset: CaptionPreset;
  fontFamily: string;
  fontSize: "sm" | "base" | "lg" | "xl";
  position: "top" | "middle" | "bottom";
  textColor: string;
  highlightColor: string;
  karaokeSync: boolean;
}

export interface ClipEditSettings {
  clipName: string;
  startSec: number;
  endSec: number;
  aspectRatio: AspectRatioMode;
  autoReframe: boolean;
  motionSmoothing: number; // 0 to 100
  splitScreen: boolean;
}

export interface ExportSettings {
  fileName: string;
  resolution: "1080p" | "4k" | "720p";
  format: "mp4" | "mov";
  burnInSubtitles: boolean;
}
