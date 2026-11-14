# Captions

## Overview
Caption styling translator converting user-facing UI caption options into backend ASS subtitle formatting parameters.

## Interface
- style.ts: buildCaptionStyle - Function mapping CaptionStyleOptions to ASS PlayRes and margin pixel values

## Invariants
- Resolves font size pills ('sm' | 'base' | 'lg' | 'xl') to exact ASS PlayRes pixel values (76, 94, 110, 132)
- Maps style presets ('neon-glow', 'minimalist', 'bold-outline', 'cyberpunk') to concrete outline widths, shadow depths, and default highlight colors

## Side Effects
- None

## Verification
- Run: `npm --prefix frontend test`
