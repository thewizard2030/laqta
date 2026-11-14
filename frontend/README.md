# Laqta Frontend

## Overview
Laqta studio frontend subsystem — a local-first React 19 + TypeScript + Vite + Tailwind CSS long-video-to-Shorts workbench connecting to a local Python FastAPI backend at 127.0.0.1:8000.

## Interface
- package.json: laqta-frontend - Project manifest defining React 19, Vite, Tailwind CSS, Lucide icons, and testing toolchain
- vite.config.ts: Vite configuration with React plugin, path aliases (@ -> src), and API proxying to http://127.0.0.1:8000
- tsconfig.json: TypeScript compiler configuration with strict mode and JSX transform
- index.html: HTML shell mounting #root with dark theme styling
- [src](./src/README.md): Application source tree containing components, features, lib, and types
- [public](./public/README.md): Static web assets and branding favicon

## Invariants
- Local-first operation: All media, transcripts, and render files remain on local device (127.0.0.1)
- No external cloud API calls without explicit operator opt-in (allow_cloud_apis=true)
- RTL-safe Arabic caption rendering using explicit direction detection and CSS bidi plaintext properties

## Side Effects
- Network communication strictly targeted at 127.0.0.1:8000 via /api/*

## Verification
- Run: `npm --prefix frontend test`
