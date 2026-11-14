# Laqta Brand Kit

A clean, editable vector identity based on the Laqta direction: a geometric **L**, a play triangle, and three frame cues.

## Included

- `svg/laqta-app-icon.svg` — square gradient app icon.
- `svg/laqta-symbol.svg` — transparent standalone symbol.
- `svg/laqta-logo-dark.svg` / `laqta-logo-light.svg` — horizontal primary lockups.
- `svg/laqta-logo-monochrome-*.svg` — single-color variants.
- `svg/laqta-wordmark-*.svg` — wordmark-only variants.
- `svg/favicon.svg` — compact favicon.
- `svg/laqta-brand-banner.svg` — 1600×600 brand banner.
- `png/` — ready-to-use raster exports, including icon sizes 16–1024 px.

## Brand colors

| Token | Hex | Usage |
|---|---|---|
| Ink | `#070A14` | Main dark background |
| Deep Navy | `#10162B` | Light-mode text |
| Violet | `#A72BFF` | Gradient start |
| Purple | `#5637F5` | Gradient middle |
| Cyan | `#00C9E8` | Gradient end |
| White | `#F8FAFF` | Dark-mode logo |
| Muted | `#AAB6CC` | Secondary text on dark backgrounds |

## Typography

The SVG wordmarks use live text (not outlined paths) to remain editable. Recommended fonts: **Manrope ExtraBold** for the wordmark and **Inter** for supporting text. Fallbacks are included in the SVG font stack. Install the fonts locally if exact rendering consistency is required.

## Usage

- Use dark logo on dark surfaces and light logo on white/light surfaces.
- Use the app icon for app launchers and social avatars.
- Use `favicon.svg` for browser tabs.
- Avoid stretching the mark or changing the gradient direction.
- Keep clear space around the icon at least equal to the width of one frame cue.

## Important implementation note

These are newly authored vector assets inspired by the approved visual direction. The SVGs are editable source files; wordmark text remains text so it can be changed in a vector editor. For production use, convert the text to outlines in Figma/Inkscape if you need identical wordmark rendering on machines without the recommended fonts.
