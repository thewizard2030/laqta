# Studio

## Overview
Main studio shell orchestrating the left sidebar navigation, top header with global search and breadcrumbs, center workbench area, and persistent bottom pipeline milestone status bar.

## Interface
- StudioLayout.tsx: StudioLayout - Top-level layout container coordinating sidebar, header, workbench, and status bar
- StudioSidebar.tsx: StudioSidebar - Collapsible navigation sidebar supporting project, dashboard, and settings tabs
- StudioSidebar.tsx: StudioNavTab - Tab identifier union ('projects' | 'studio' | 'settings')
- StudioTopHeader.tsx: StudioTopHeader - Header bar with breadcrumbs, project name editing, and global search
- StudioStatusBar.tsx: StudioStatusBar - Bottom bar showing hardware runtime status and pipeline milestones
- ProjectPoster.tsx: ProjectPoster - Media backdrop and project metadata summary display
- [Canvas](./canvas/README.md): Canvas preview viewport and player controls
- [Clips](./clips/README.md): AI-suggested candidate clips and transcript browser
- [Inspector](./inspector/README.md): Sidebar inspector for editing, captions, and export
- [Timeline](./timeline/README.md): Interactive multi-track timeline editor

## Invariants
- Keyboard accessibility skip link (#studio-main-content) is always rendered at the top of the layout
- Hardware status pill honestly indicates degraded state if the backend background worker is stopped
- Status bar pipeline milestones reflect real project state (video loaded, transcript ready, clips generated, storage writable)

## Side Effects
- Binds fullscreen change listener to keep fullscreen toggle synchronized
- Listens for Escape key to close mobile drawer navigation
- Binds global Ctrl+K / Cmd+K listener to focus header search input

## Verification
- Run: `npm --prefix frontend test`
