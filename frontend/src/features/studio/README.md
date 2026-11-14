# Studio

## Overview
Shared type contracts for the studio editor workbench, defining aspect ratio modes, inspector tabs, caption style presets, clip edit settings, and export parameters.

## Interface
- types.ts: AspectRatioMode - Aspect ratio string union ('9:16' | '16:9' | '1:1')
- types.ts: InspectorTab - Active tab union ('edit' | 'captions' | 'export')
- types.ts: CaptionPreset - Subtitle style presets ('neon-glow' | 'minimalist' | 'bold-outline' | 'cyberpunk')
- types.ts: CaptionStyleOptions - Configuration interface for font, size, outline, and positioning
- types.ts: ClipEditSettings - Cut start/end, crop mode, and reframe parameters
- types.ts: ExportSettings - Render resolution, CRF quality, and subtitle burn settings

## Invariants
- Preserves discrete values for aspect ratio modes and caption presets across editor tabs

## Side Effects
- None

## Verification
- Run: `npm --prefix frontend test`
