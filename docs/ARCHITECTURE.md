# Laqta Architecture

How the pieces fit together, and where to change things. For the *contract*
with users (what leaves the machine, rights, licences) see
[POLICY.md](POLICY.md); for the product requirements see [PRD.md](PRD.md).

---

## 1. The shape of the system

```text
┌──────────────────────────────┐        ┌──────────────────────────────┐
│  Browser (React + Vite)      │◀──────▶│  FastAPI (127.0.0.1:8000)    │
│  frontend/src                │  HTTP  │  backend/app                 │
└──────────────────────────────┘        └───────────┬──────────────────┘
        │                                        │        │
        │  reads /api/capabilities               │        │  reads + writes
        │  (what is really installed)            │        ▼
        ▼                                        │  ┌───────────────────────┐
  honest UI, never a guess                     └──▶│  SQLite (WAL)         │
                                                     │  projects, media,     │
                                                     │  transcripts, clips   │
                                                     └───────────┬───────────┘
                                                                 │
                          ┌──────────────────────────────────────┘
                          ▼
                 ┌────────────────────┐        ┌──────────────────────────┐
                 │  qatta/ (core)     │◀──────▶│  qatta_manifest.json    │
                 │  manifest pipeline │        │  one file per project,  │
                 │  s01 → s07         │        │  atomic, resumable      │
                 └─────────┬──────────┘        └──────────────────────────┘
                           │ subprocess (argv arrays, no shell)
                           ▼
                 ffmpeg · ffprobe · faster-whisper · yt-dlp
```

**Three processes, one source of truth.** The browser never decides what is
possible — it asks `/api/capabilities`. The core pipeline never talks to the
browser — it advances a manifest on disk. The API is the only place where the
two meet, and it translates the manifest into database rows
(`backend/app/services/bridge/manifest_sync.py`).

## 2. The manifest is the state

`qatta/core/schema.py` defines `QattaManifest` — a Pydantic v2 model that is
validated strictly and written atomically to
`<data_dir>/projects/<id>/qatta_manifest.json`.

```text
completed_stages: ["s01_ingest", "s02_transcript", ...]
atomic_utterances: [ {u_id: "U_0001", start_ms, end_ms, text, words[]} ]
candidates:       [ {clip_id, start_u_id, end_u_id, cps, rationale, ...} ]
stage_timings_ms: {"s02_transcript": 41230}
```

Three rules make it trustworthy:

1. **A stage whose name is in `completed_stages` is skipped** unless
   `force=True`. The pipeline resumes exactly where it stopped, even after a
   crash or a restart.
2. **The file is written atomically** (temp file + rename), so a crash can
   never leave a half-written manifest.
3. **`stage_timings_ms` holds measured wall time** per stage. Every performance
   claim in the docs points at these numbers, never at an estimate.

### The stages

| Stage | Module | Does |
|-------|--------|------|
| `s01_ingest` | `qatta/stages/s01_ingest/` | Copy/probe the source, extract 16 kHz audio, or pull a YouTube caption track |
| `s02_transcript` | `qatta/stages/s02_transcript/` | Pass 1 (fast, segment level) and Pass 2 (word level, only for the winning clips) |
| `s03_multimodal` | `qatta/stages/s03_multimodal/` | Scene cuts, audio features, optional face/landmark analysis |
| `s04_candidates` | `qatta/stages/s04_candidates/` | Propose clip candidates; optionally let an LLM *rerank* them (never invent timestamps) |
| `s05_ranking` | `qatta/stages/s05_ranking/` | The deterministic Clip Potential Score with its per-signal rationale |
| `s05b_section_fetch` | `qatta/stages/s05b_section_fetch/` | Download only the sections the ranker selected |
| `s06_reframe_subs` | `qatta/stages/s06_reframe_subs/` | 9:16 reframing, Arabic BiDi caption shaping, ASS export |
| `s07_render_learn` | `qatta/stages/s07_render_learn/` | Render the MP4 and feed the result back into the project |

**The LLM boundary:** a model may only ever reference `u_id` values
(`U_0001`, …). It never sees or returns raw timestamps — those are measured,
not generated.

## 3. The API

| Route | Purpose |
|-------|---------|
| `GET /api/health` | Liveness + the running version |
| `GET /api/capabilities` | **The honest capability report** — what is installed, what is optional, what is missing |
| `GET/POST /api/projects` | The project store |
| `POST /api/projects/{id}/media` | Import a local file (or a gated URL) |
| `POST /api/media/{id}/transcription-jobs` | Queue a transcription job |
| `GET /api/media/{id}/candidates` | The ranked candidates with their rationale |
| `POST /api/media/{id}/candidates` | Generate candidates from a transcript |
| `GET /api/projects/{id}/jobs` | The job history (the UI polls this) |
| `POST /api/candidates/{id}/render` | Render a vertical MP4 |
| `GET /api/jobs/{id}/events` | Server-sent progress for a running job |

Jobs never run inside a request handler: the API enqueues, a **single worker**
executes, and the state is persisted so a restart can recover it.

## 4. The frontend

```text
frontend/src/
  App.tsx                    # the shell: loads health + capabilities + projects
  lib/
    api/client.ts            # typed API client (timeouts, typed errors)
    brand.ts                 # the product name and every outbound URL
    i18n/bidi.ts             # FSI/PDI isolates and RTL shaping helpers
    captions/style.ts        # caption style presets
    rationale.ts             # picking the first meaningful rationale line
  features/
    dashboard/               # the home screen
    projects/                # the project detail view (the workbench)
    clips/                   # the candidate review panel
    transcription/           # the transcript viewer
  components/
    studio/clips/            # the clip list
    studio/canvas/           # the 9:16 preview + karaoke captions
    studio/timeline/         # the multi-track timeline
    studio/inspector/        # Edit / Captions / Export
    ui/                      # Button, Modal, Toast, BrandLogo, LaqtaMark, BrandIcons
```

Two rules the UI follows:

- **It never guesses.** Every panel that depends on a capability reads it
  from `/api/capabilities` and shows the *reason* when something is missing.
- **One accent system.** `laqta-*` violet is the brand and every "active"
  state; cyan is reserved for live state (the playhead, a running job, the
  active range). See [BRANDING.md](BRANDING.md).

## 5. Where to change things

| I want to… | Touch |
|-------------|-------|
| Add a pipeline stage | `qatta/stages/sNN_*/` + register it in `qatta/core/pipeline.py` |
| Change how clips are scored | `qatta/stages/s05_ranking/scorer.py` (+ the rationale strings) |
| Change the caption layout | `backend/app/services/captions/generator.py`, `frontend/src/lib/i18n/bidi.ts` |
| Add an API route | `backend/app/api/routes/` + a schema in `backend/app/schemas/` |
| Change the studio layout | `frontend/src/components/studio/` |
| Change the brand | `frontend/src/lib/brand.ts` + `frontend/src/index.css` (`@theme`) |

## 6. Running it

```bash
./scripts/setup.sh     # one-time
./scripts/dev.sh       # API + studio
./scripts/check.sh     # every quality gate (the same ones CI runs)
```

The CLI mirrors the same structure:

```bash
laqta doctor    # what is installed, what is running
laqta serve     # the API only
laqta studio    # the API and the studio together
laqta models    # the locally cached speech models
```

## 7. Testing

| Suite | Command | Scope |
|-------|---------|-------|
| Core pipeline | `pytest tests` | The manifest stages, end to end, without a server |
| Backend API | `pytest` (in `backend/`) | The routes, the job queue, the database bridge |
| Frontend | `npm run test` | The components and the hooks |

Both Python suites are **hermetic**: they redirect the data directory into a
temporary folder and neutralise any hosted-provider opt-in from a local
`.env`, so a test can neither touch your real projects nor reach a third
party.

Coverage is measured in CI and gated on non-regression
(`config/coverage-baseline.json`).
