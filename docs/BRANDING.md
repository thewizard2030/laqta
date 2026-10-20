# Laqta — Brand & UI System

This document records the product identity of **Laqta** (لقطّة) and the design
decisions behind the recreated dashboard. It is the reference for any future
brand or UI work in this repository.

---

## 1. Name

| Form | Value | Where it is used |
|------|-------|------------------|
| Latin wordmark | `Laqta` | App title, wordmark, export filenames, backend `APP_NAME` |
| Arabic wordmark | `لقطّة` | Badge next to the Latin wordmark, fake-ASR sample text |
| Meaning | "a take / a cut" | Matches the product promise: turning long videos into cuts |

`Laqta` is a neutral, pronounceable Latin spelling, so it works in file
names, CLI output and logs, while the Arabic badge keeps the Arabic-first
identity visible in the product UI.

### Identifiers that intentionally keep their old name

Renaming these would break existing local data or operator configuration, so
the rebrand left them untouched:

- Python package `qatta/` and the classes `QattaManifest` / `QattaSettings`
- On-disk manifest `qatta_manifest.json` (per project)
- Environment variable prefix `QATTA_*` (e.g. `QATTA_ENABLE_URL_INGESTION`)
- Local data directory `~/.local/share/qatta`

---

## 2. Colour system

The palette lives in `frontend/tailwind.config.js` and `frontend/src/index.css`
(`--laqta-gradient` plus the `--surface-*` / `--text-*` ramps).

| Token | Value | Role |
|-------|-------|------|
| `laqta-600` | `#7c4dff` | Brand primary, primary CTA, focus ring |
| `laqta-500` | `#8b5cf6` | Gradient midpoint, icon tiles |
| `laqta-200` | `#ddd6fe` | Brand text on dark surfaces |
| `neon.cyan` | `#22d3ee` | Secondary accent, local/engine status |
| `neon.emerald` | `#10b981` | "ready" state |
| `neon.amber` | `#f59e0b` | "missing component" state |
| `obsidian-950 … 800` | `#070A11 … #141C30` | Surface ramp (app → inputs) |

The identity gradient is **violet → cyan** (`--laqta-gradient`), applied to
the wordmark, the primary CTA, the dashboard headline and the range-slider
thumb. Amber is reserved for missing components, so it is never used as a
brand accent.

Surfaces stay dark on purpose: the app is a video workbench that is used next
to a video preview, and `color-scheme: dark` is declared globally.

### The one-accent rule

The studio used to mix purple, fuchsia, indigo and cyan everywhere. The
current system has exactly two accents with fixed meanings:

| Accent | Meaning | Where |
|--------|---------|-------|
| `laqta-*` (violet) | **Brand, active and selected UI** | Selected clip card, active inspector/clips tab, primary CTA, focus rings, active aspect-ratio tile, job progress while running |
| `neon-cyan` | **Live state only** | Timeline playhead, waveform, running job, speaker-crop guide, "Clip / Full" scrubber mode |
| emerald / amber / red | Status | Ready · missing component · error |

Neutral (`slate`) icons carry the media specification strip; the values stay
the loud part. Never introduce a fourth accent for decoration.

---

## 3. Typography

The app keeps the **system font stack** (no webfont request). Laqta is
local-first and must work fully offline, and a Google Fonts `<link>` would
either fail offline or add a network dependency to a product whose main
promise is that nothing leaves the machine.

Hierarchy comes from weight, size and colour instead:

- Headlines: `font-black tracking-tight`
- Section labels: `text-[11px] font-semibold uppercase tracking-wider`
- Technical values: `font-mono text-[10px]` (versions, resolutions, paths)

---

## 4. Logo

`frontend/src/components/ui/LaqtaMark.tsx` is an inline SVG: a rounded
"L" monogram (stem = timeline, foot = the cut) on the violet→cyan gradient,
with a diagonal notch on the shoulder. Inline SVG keeps the mark crisp at
every size, themeable, and free of a binary asset.

| Asset | Purpose |
|-------|---------|
| `frontend/src/components/ui/LaqtaMark.tsx` | The mark itself (inline SVG, used everywhere in the app) |
| `frontend/public/favicon.svg` | The browser tab icon |
| `frontend/public/logo.png` | A 512 px raster fallback (56 KB, 8-bit) |
| `docs/assets/laqta-logo.png` | The full wordmark for the docs and the README |

The wordmark pairs the Latin **Laqta** with the Arabic **لقطّة**. The
raster wordmark is rendered with the Noto Sans Arabic face so the Arabic
is properly shaped — never isolated letterforms.

To change the mark, edit the SVG in `frontend/public/favicon.svg` and the
component in `frontend/src/components/ui/LaqtaMark.tsx`; they must stay in
sync.

---

## 5. Dashboard layout (recreated)

```
┌──────────────────────────────────────────────┬───────────────────────┐
│ HERO — import & drop zone                    │ 4 KPI tiles           │
│  local-only chip · headline · CTAs · notes   │ workspaces / media    │
│                                              │ footage / disk        │
├──────────────────────────────────────────────┴───────────────────────┤
│ LOCAL ENGINE STATUS — honest, probed live                            │
├──────────────────────────────────────────────┬───────────────────────┤
│ CONTINUE WHERE YOU LEFT OFF — recent workspaces (max 4)              │
├──────────────────────────────────────────────┴───────────────────────┤
│ HOW LAQTA WORKS — import → transcribe → rank → render                 │
└──────────────────────────────────────────────────────────────────────┘
```

Principles that must survive future edits:

1. **The import path is the hero.** A dropped or picked file is the fastest
   way into the pipeline, so it is the largest, brightest element.
2. **Real numbers only.** The KPI tiles are computed from the project list
   (workspaces, media assets, total footage, bytes on disk) — never mock values.
3. **Honest engine state.** Every tile mirrors `GET /api/capabilities`;
   optional components are labelled *Optional*, missing ones *Missing*. A
   hosted LLM is never described as local.
4. **The pipeline strip describes the product**, not a live job state.
5. **A single visual language** with the rest of the app: `.laqta-card`,
   `.laqta-gradient-text`, `.laqta-gradient-surface` and the `laqta-*` /
   `neon-*` Tailwind ramps.

Accessibility notes: drop-and-drop always has a keyboard-reachable button
alternative, focus rings are visible on every control, the state badges pair
colour with a text label (never colour alone), and `prefers-reduced-motion`
is honoured globally in `src/index.css`.

---

## 6. Studio (project detail) rules

The workbench follows the same system, plus a few rules of its own:

1. **Card = button.** A clip card is a `<li>` that contains one stretched
   `<button>` (the selection target) — never a `role="button"` div with a
   nested button. The card's rationale line comes from the first *substantive*
   rationale entry; the backend's `Overall rationale …` header is skipped so
   the row is never empty.
2. **Long lists are paged.** The clip list mounts the first 20 cards and adds
   the rest through a "Show 20 more" button. No list is allowed to mount
   hundreds of nodes.
3. **The preview sits on a stage.** The area around the vertical canvas uses
   `.laqta-stage-grid` + `.laqta-stage-glow`, and a title-safe guide marks
   where text stays readable in 9:16.
4. **Jobs are rows, not cards.** One line for status/type/id, one thin
   progress bar with the percentage and stage inline, one line of timestamps.
5. **Nothing may be implied.** The engine strip, the job states and the
   caption readiness all report what the backend actually returned.

---

## 7. Checklist before shipping UI changes

- [ ] No emoji used as an icon (Lucide / inline SVG only)
- [ ] `npm run typecheck` and `npm run test` pass
- [ ] Contrast ≥ 4.5:1 for body text in both themes
- [ ] Focus ring visible on every interactive element
- [ ] Reduced motion respected
- [ ] Layout verified at 375 px, 768 px, 1024 px and 1440 px
- [ ] No capability is claimed that the backend does not report
