# Laqta — Official Brand & UI System

This document records the official product identity of **Laqta** (لقطة) and the design system implemented across the application. It serves as the single reference for visual identity, design tokens, asset locations, and component styling conventions.

---

## 1. Product Identity

| Attribute | Value | Description & Context |
|---|---|---|
| **Product Name** | `Laqta` | Official Latin brand name and application display title |
| **Arabic Name** | `لقطة` | Official Arabic wordmark / badge ("a take / a cut") |
| **Tagline** | `Long Videos to Viral Shorts` | Core product promise across web, desktop, and marketing |
| **Visual Direction** | Premium, modern, creator-focused, dark-first | Optimized for video creator workbenches and dark room editing |
| **Platform Target** | Linux/Fedora-first desktop application | Native FreeDesktop packaging (`.desktop`) with high-resolution icon suites |

---

## 2. Official Brand Palette

The palette is extracted directly from the official **Laqta Brand Kit** vector definitions.

### Core Brand Tokens

| Token Name | CSS Variable | Hex / RGBA | Usage & Semantic Role |
|---|---|---|---|
| **Ink** | `--laqta-background` / `--surface-0` | `#070A14` | Primary dark workspace background |
| **Deep Navy** | `--laqta-surface-elevated` | `#10162B` | Elevated panels, cards, and light-mode text anchor |
| **Violet** | `--laqta-violet` | `#A72BFF` | Brand gradient start, active item accents, glow highlights |
| **Purple** | `--laqta-primary` | `#5637F5` | Brand gradient middle, primary buttons, brand selections |
| **Cyan** | `--laqta-cyan` | `#00C9E8` | Brand gradient end, live state, playhead, active timers |
| **White** | `--laqta-text` | `#F8FAFF` | Primary typography and vector icon highlights on dark |
| **Muted** | `--laqta-muted` | `#AAB6CC` | Secondary body copy, subtitle labels, metadata text |
| **Surface** | `--laqta-surface` / `--surface-2` | `#0E1424` | Workbench panels, card backgrounds, raised areas |
| **Hairline** | `--laqta-border` / `--hairline` | `rgba(148, 163, 184, 0.14)` | Subtle 1px dividers and surface borders |

### Functional Status Tokens

| Role | Token | Hex | Where Used |
|---|---|---|---|
| **Live State / Scrubber** | `--color-neon-cyan` | `#00C9E8` | Timeline playhead, waveform, active scrubber mode |
| **Success / Ready** | `--color-neon-emerald` | `#10B981` | Engine ready, FFmpeg verified, export complete |
| **Warning / Notice** | `--color-neon-amber` | `#F59E0B` | Missing optional engine, unsaved changes |
| **Danger / Error** | `--danger` | `#F87171` | API offline, rejected files, failed jobs |

### Brand Gradient

```css
/* Official Brand Gradient */
--laqta-gradient: linear-gradient(120deg, #A72BFF 0%, #5637F5 48%, #00C9E8 100%);
```

Applied to:
- Primary CTA action buttons (`.laqta-gradient-surface`)
- Hero headline emphasis (`.laqta-gradient-text`)
- Playhead and scrubber progress fills
- Interactive range-slider thumbs

---

## 3. Official Logo Geometry & Mark

The official Laqta mark combines three distinct elements:
1. **Geometric L Monogram**: Represents the timeline (vertical stem) and the cut (horizontal foot):
   `M270 240 H408 V648 H750 V786 H338 C300 786 270 756 270 718 Z`
2. **Playback Triangle**: Positioned inside the counter of the L:
   `M492 350 L680 470 L492 590 Z`
3. **Three Vertical Frame Cues**: Three rounded cues on the right representing video frames:
   `rect x="742" y="242/352/462" width="70" height="70" rx="15"`

### Supported Variants in `LaqtaMark.tsx`

- `variant="badge"`: The square gradient app icon with rounded corners (`rx="220"`), diagonal cut shadow, and crisp white geometry.
- `variant="symbol"`: Standalone mark with transparent background, gradient L, white playback triangle, and gradient frame cues.
- `variant="monochrome"`: Clean single-color vector mark inheriting `currentColor` or solid white.

### Logo Usage Rules

- Use `laqta-logo-dark.svg` (or `BrandLogo` with dark theme) on dark backgrounds (`#070A14` to `#10162B`).
- Use `laqta-logo-light.svg` on light backgrounds.
- Maintain at least the clear space of one frame cue (`70px` relative to `1024px` viewBox) around the mark.
- Never stretch, squash, rotate, or alter the gradient direction (`120deg` Violet → Purple → Cyan).

---

## 4. Asset Locations

### Verified Master Brand Assets (`Laqta_Brand_Kit/`)

- `Laqta_Brand_Kit/svg/laqta-app-icon.svg` — 1024×1024 master application icon.
- `Laqta_Brand_Kit/svg/laqta-symbol.svg` — 1024×1024 standalone transparent symbol.
- `Laqta_Brand_Kit/svg/laqta-logo-dark.svg` — Horizontal dark-surface lockup (1500×390).
- `Laqta_Brand_Kit/svg/laqta-logo-light.svg` — Horizontal light-surface lockup (1500×390).
- `Laqta_Brand_Kit/svg/favicon.svg` — 64×64 compact browser favicon.
- `Laqta_Brand_Kit/svg/laqta-brand-banner.svg` — 1600×600 promotional brand banner.
- `Laqta_Brand_Kit/png/` — Full resolution raster suite (`laqta-icon-16.png` through `laqta-icon-1024.png`).

### Runtime Application Assets (`frontend/public/`)

- `frontend/public/favicon.svg` — Browser tab SVG icon.
- `frontend/public/favicon-32.png` — Standard 32px favicon fallback.
- `frontend/public/favicon-64.png` — Retina 64px favicon.
- `frontend/public/laqta-icon-192.png` — Web / PWA 192px icon.
- `frontend/public/laqta-icon-512.png` — High-res 512px icon.
- `frontend/public/logo.png` — 512px fallback asset.
- `frontend/public/laqta-logo-dark.svg` & `laqta-logo-light.svg` — Vector lockups.
- `frontend/public/laqta-symbol.svg` — Vector symbol.

### Desktop & Linux Packaging (`packaging/`)

- `packaging/laqta.desktop` — FreeDesktop application launcher specification for Linux/Fedora.
- `packaging/icons/hicolor/{16x16,32x32,48x48,64x64,128x128,192x192,256x256,512x512,scalable}/apps/` — Full standard Linux icon theme hierarchy.

---

## 5. Typography & Bilingual Arabic Layout

1. **Font Hierarchy**:
   - Primary Headings: `Manrope`, `Inter`, system-ui (`font-black tracking-tight`).
   - Body & Controls: System font stack (`-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto`).
   - Technical & Telemetry: `font-mono` (`ui-monospace, SFMono-Regular, Consolas`).
   - Arabic Wordmark & Captions: `Noto Sans Arabic`, `Vazirmatn`, `Droid Arabic Kufi`.
2. **Arabic Layout & BiDi**:
   - Bilingual badge: `<span dir="rtl">لقطة</span>` paired with `Laqta`.
   - Arabic text rendering respects proper RTL directionality, cursive shaping, and Unicode isolation (`FSI`/`PDI` and `RLM`).

---

## 6. Component Styling Conventions

1. **Surfaces**:
   - Base canvas: `.studio-ambient` on `#070A14` with soft violet/cyan radial backlighting.
   - Cards & Panels: `.laqta-card` with `var(--hairline)` border and 1px top highlight.
   - Stage workbench: `.laqta-stage-grid` with `.laqta-stage-glow` behind the vertical canvas.
2. **Focus Rings**:
   - Universal accessible outline: `focus-visible:ring-2 focus-visible:ring-laqta-400 focus-visible:ring-offset-2 focus-visible:ring-offset-obsidian-950`.
3. **Empty States**:
   - Powered by `<EmptyState type="projects" | "media" | "clips" | "transcript" />`.
   - Restrained, informative messaging without artificial clutter.
4. **Motion & Transitions**:
   - Subtle entrance animations: `.animate-fadeIn` (160ms), `.animate-fadeUp` (220ms).
   - All animations strictly respect `@media (prefers-reduced-motion: reduce)`.
