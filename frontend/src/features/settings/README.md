# Settings

## Overview
Studio settings and engine management view, coordinating drafts of user preferences, BYOK credentials, factory reset dialogs, and unsaved changes tracking across settings categories.

## Interface
- SettingsView.tsx: SettingsView - Multi-tab settings studio workbench with unsaved change tracking and save/reset actions
- SettingsView.tsx: SettingsTabId - Tab union ('ai' | 'speech' | 'ingest' | 'storage' | 'system')
- [Tabs](./tabs/README.md): Concrete settings tab panels

## Invariants
- Unsaved draft changes trigger an interactive warning badge and allow discarding or batch saving
- Factory reset requests confirmation via ConfirmDialog before invoking POST /api/settings/reset

## Side Effects
- Fetches settings from GET /api/settings
- Persists settings updates to PATCH /api/settings
- Resets configuration to defaults via POST /api/settings/reset

## Verification
- Run: `npm --prefix frontend test`
