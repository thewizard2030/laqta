# Inspector

## Overview
Studio sidebar inspector panel with tabbed navigation ('edit', 'captions', 'export') for configuring clip cut points, auto-reframe, motion smoothing, ASS caption styles, and local FFmpeg export rendering.

## Interface
- InspectorPanel.tsx: InspectorPanel - Sidebar tab container coordinating Edit, Captions, and Export configurations
- EditTabContent.tsx: EditTabContent - Clip cut window tuning, duration warnings, and active speaker auto-reframe settings
- CaptionsTabContent.tsx: CaptionsTabContent - Subtitle presets, font selection, size scaling, and outline styling
- ExportTabContent.tsx: ExportTabContent - Resolution selection, CRF quality, burned-in subtitles toggle, and render dispatch

## Invariants
- Tab navigation is strictly constrained to InspectorTab ('edit' | 'captions' | 'export')
- Font selections are restricted to verified Arabic and Latin system font families
- Export jobs strictly target local FFmpeg with burned-in subtitles and 9:16 vertical crop

## Side Effects
- Mutates ClipEditSettings, CaptionStyleOptions, and ExportSettings via update callbacks
- Triggers onExport callback to enqueue background rendering job on backend

## Verification
- Run: `npm --prefix frontend test`
