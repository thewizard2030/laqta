# Canvas

## Overview
Vertical Shorts canvas preview viewport, aspect ratio selector (9:16 portrait, 16:9 widescreen, 1:1 square), live karaoke caption overlay, face-tracking crop guide, and interactive playback scrubber controls.

## Interface
- ShortsCanvasPlayer.tsx: ShortsCanvasPlayer - Main interactive video canvas component with aspect ratio selection and crop guide
- ShortsCanvasPlayer.tsx: AspectRatioType - Type union ('9:16' | '16:9' | '1:1') defining supported aspect ratios
- LiveKaraokeCaption.tsx: LiveKaraokeCaption - Real-time word-by-word highlighted caption overlay with RTL/LTR directional support
- LiveKaraokeCaption.tsx: CaptionStyleConfig - Visual styling configuration for caption text, outline, and highlights
- PlayerControlsBar.tsx: PlayerControlsBar - Playback transport controls (play, pause, seek, volume, speed, loop toggle)

## Invariants
- Phone frame preview strictly preserves container aspect ratio (9:16, 16:9, or 1:1) without squashing video frames
- Active speaker framing crop guide is only displayed in 9:16 portrait mode when enabled
- In clip scrubber mode with auto-loop enabled, playback loops back to clipWindow.startSec upon reaching clipWindow.endSec
- Captions determine direction from first strong directional character and clean raw text before rendering

## Side Effects
- Controls HTML5 video element playback, seeking, volume, and muting
- Fires playback state and aspect ratio update callbacks to parent studio workbench

## Verification
- Run: `npm --prefix frontend test`
