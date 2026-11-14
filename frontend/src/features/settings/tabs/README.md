# Tabs

## Overview
Detailed tab panels for application settings: BYOK AI provider keys & live key verification, speech recognition profiles & Arablish prompting, yt-dlp URL ingestion policies & cookie configuration, disk storage usage & transcript cache clearing, and live engine diagnostics.

## Interface
- AiProvidersTab.tsx: AiProvidersTab - BYOK key configuration, model selection, and live connection testing
- SpeechRecognitionTab.tsx: SpeechRecognitionTab - Whisper profile selection, device configuration, and Arablish prompt tuning
- IngestionTab.tsx: IngestionTab - URL ingestion feature flag, subtitle language priorities, and cookies
- StorageCacheTab.tsx: StorageCacheTab - Disk usage gauges, cached transcripts listing, and cache purge actions
- SystemAuditTab.tsx: SystemAuditTab - Engine diagnostics audit wrapper with manual re-probe trigger

## Invariants
- BYOK API keys are tested live via POST /api/settings/verify before saving
- Master cloud APIs switch (allow_cloud_apis) fail-closes all outbound cloud calls when disabled
- Clearing transcript cache deletes cached audio fingerprints but leaves project media and metadata intact

## Side Effects
- Verifies API keys via api.verifyKey
- Clears transcript cache via api.clearTranscriptCache
- Re-probes engine capabilities via onRefreshCapabilities

## Verification
- Run: `npm --prefix frontend test`
