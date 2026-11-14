# Dashboard

## Overview
Studio dashboard landing screen providing instant video drag-and-drop import, workspace activity statistics (footage duration, storage bytes), local engine runtime health inspection, recent workspaces navigation, and gated YouTube URL ingestion.

## Interface
- DashboardHome.tsx: DashboardHome - Main dashboard view with drag-and-drop import and recent projects list
- EngineStatusStrip.tsx: EngineStatusStrip - Header strip displaying local FFmpeg, Whisper, and storage health
- YouTubeTargetModal.tsx: YouTubeTargetModal - Destination project selector modal for imported YouTube URLs

## Invariants
- Direct video drop triggers automatic project creation and immediate media asset upload
- YouTube ingestion button is disabled if url_ingestion.feature_flag is false or yt_dlp is unavailable, citing the exact system constraint
- Engine status strip audits live backend capabilities (/api/capabilities) with distinct ready/missing/optional indicators

## Side Effects
- Initiates video uploads via onDirectVideoDrop
- Creates destination workspaces for YouTube URL imports via onCreateWorkspace
- Queues URL ingestion jobs via api.ingestMediaFromUrl

## Verification
- Run: `npm --prefix frontend test`
