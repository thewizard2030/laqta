# Components

## Overview
Top-level application feedback components, privacy and local processing guarantee banner, empty project states, offline backend connection error panels with retry command copying, loading skeleton placeholders, and runtime capability cards.

## Interface
- PrivacyBanner.tsx: PrivacyBanner - Banner informing users of local-first privacy guarantees and opt-in cloud status
- EmptyState.tsx: EmptyState - Generic placeholder illustration and message for empty lists
- ErrorMessage.tsx: ErrorMessage - Backend disconnection alert box providing restart CLI commands
- LoadingSkeleton.tsx: LoadingSkeleton - Animated pulse skeleton placeholder for async data loading
- CapabilitiesCard.tsx: CapabilitiesCard - Real-time audit card of local engine capabilities (FFmpeg, Whisper, PyTorch)
- [Studio](./studio/README.md): Studio shell and layout components
- [UI](./ui/README.md): Reusable UI primitives and modal dialogs

## Invariants
- PrivacyBanner explicitly highlights opt-in hosted disclosure if OpenRouter API is configured and enabled
- ErrorMessage displays exact local uvicorn command for restarting backend server
- CapabilitiesCard reflects true status of local FFmpeg, FFprobe, faster-whisper, and storage permissions without mock successes

## Side Effects
- Copies backend restart command to system clipboard via navigator.clipboard.writeText
- Fires retry connection callbacks

## Verification
- Run: `npm --prefix frontend test`
