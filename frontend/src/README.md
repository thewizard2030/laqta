# Frontend Source

## Overview
Frontend application root module, React entry point (main.tsx), and root application orchestrator (App.tsx) managing global health, active project selection, global search, and tab switching.

## Interface
- App.tsx: App - Root application component coordinating state across Projects, Studio, and Settings
- main.tsx - Application entry point mounting React root with ErrorBoundary
- [Components](./components/README.md): Studio layout, canvas, clips, inspector, timeline, and UI primitives
- [Features](./features/README.md): Domain feature modules (clips, dashboard, projects, transcription, settings)
- [Lib](./lib/README.md): Shared client utilities, API client, i18n, and caption styling
- [Types](./types/README.md): Core TypeScript domain models and API schema interfaces

## Invariants
- Encapsulates entire studio in ErrorBoundary to prevent unhandled render crashes from blanking the screen
- Sets up global Ctrl+K / Cmd+K keyboard shortcut to focus search input
- Queries /api/health, /api/capabilities, and /api/projects in parallel on initial mount

## Side Effects
- Renders to DOM element #root
- Binds global window keydown listener for Ctrl+K search focusing

## Verification
- Run: `npm --prefix frontend test`
