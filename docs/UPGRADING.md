# Upgrading Laqta

What changed between the releases, and what you have to do.

---

## 0.3.1 → 0.4.0

**No action required for existing projects.** The data directory, the API and
the project format are backwards compatible; the new fields are additive and
the new layout is opt-in. Read on if you run `s06_reframe_subs` or want the
face-guided crop.

- **The renderer now consumes the trajectory.** `face_guided` is a supported
  layout, and `run_render_stage(layout=None)` picks it automatically when a
  candidate has a solved trajectory (otherwise it centres the crop). The
  backend render config gains `trajectory_points` and `framing_fallback`, so
  a centred fallback is distinguishable from a pan. An explicit
  `face_guided` request with nothing to follow still succeeds and records why.
- **Trajectories are rebased onto the clip's current bounds.** If you trimmed
  a candidate after the pipeline ran, the pan follows the trim instead of
  drifting.
- **Pipeline jobs can opt in over HTTP.** `POST
  /api/projects/{id}/pipeline-jobs` accepts `{"face_guided_framing": true}`;
  omitting the body keeps the previous behaviour.
- **The project format is schema version 2.** It is additive: two new optional
  fields on each candidate (`crop_trajectory`, `framing_meta`). Existing v1
  manifests still load, and nothing is migrated in place. A manifest is
  relabelled v2 the first time the reframe stage writes to it, so an older
  build will refuse it with "newer than this build understands" instead of
  failing on an unknown field.
- **Reframe captions live in `captions/reframe/`.** They used to share
  `captions/{clip_id}.ass` with the render stage, so one silently overwrote
  the other. If you read that path directly, read the new one.
- **Face-guided framing is off by default.** Turn it on with
  `QATTA_FACE_GUIDED_FRAMING=true` after installing the analysis extra
  (`pip install --require-hashes -r backend/requirements-analysis-lock.txt`).
  With it off, no frames are sampled and `framing_meta.degradation_reason`
  records that the feature is disabled.
- **The analysis extra pins `opencv-python<5`.** OpenCV 5.x stopped bundling
  the Haar cascade the detector needs, so a 5.x wheel installs fine and then
  finds no faces at all. If you manage OpenCV yourself, stay below 5 or expect
  the detector to report itself unavailable.

---

## 0.3.0 → 0.3.1

**No action required.** The data directory, the project format
(`qatta_manifest.json`, schema version 1) and the API are unchanged.

This release fixes the render stage, which was failing for anyone who ran the
pipeline rather than clicking render in the Studio:

- `s06_render` defaulted to a layout that was never implemented
  (`fill_crop`), so `laqta run` and backend job renders failed with
  `INVALID_CONFIG`. The default is now `center_crop`.
- The atomic temp file ended in `.part-<pid>`, which ffmpeg cannot map to a
  container. It now ends in `.mp4`.
- The output probe was called with the wrong arguments, so validation raised
  `TypeError` instead of checking the file.

Things worth knowing:

- **`fill_crop` is not a layout.** If you passed `layout="fill_crop"` yourself
  (it was the old default), it still raises `INVALID_CONFIG`. Use
  `center_crop` or `blurred_background`.
- **Silent sources fail loudly.** The stage requests audio unconditionally, so
  a video with no audio stream is rejected by the output probe with
  `NO_AUDIO_STREAM` rather than rendered silently.

---

## 0.2.5 → 0.3.0

**No action required.** The data directory, the project format
(`qatta_manifest.json`, schema version 1) and the API are unchanged — your
existing projects keep working.

New in this release:

- **`laqta run SOURCE`** runs the pipeline without the studio:
  `laqta run clip.mp4 --project-id demo --json`. It is the same pipeline the
  studio runs, with the same manifest and measured timings. `--stages`
  limits the run to a subset; `--force` re-runs stages already recorded as
  completed.
- The pipeline order now lives in `qatta/core/runner.py`, used by both the
  backend and the CLI. Nothing changes for existing projects.

Things worth knowing:

- **`mediapipe` is no longer part of the `[analysis]` extra.** It was never
  imported, and it pulled a second `cv2` provider
  (`opencv-contrib-python`) next to `scenedetect`'s `opencv-python`. If you
  installed `mediapipe` yourself, it is harmless but unused; nothing in
  Laqta calls it.
- **Optional profiles have their own locks:**
  `backend/requirements-url-lock.txt` and
  `backend/requirements-analysis-lock.txt`. Install with
  `pip install --require-hashes -r backend/requirements-analysis-lock.txt`.
- **`s07_render_learn` and `s06_reframe_subs` are still not wired.** They are
  libraries with tests, not pipeline stages. Do not expect them to run.
- **Ctrl-C stops at the next stage boundary.** The running stage finishes
  first; press Ctrl-C a second time to stop immediately. The manifest is
  never advanced past the last completed stage.

---

## 0.1.1 → 0.1.2

**No action required.** The API, the data directory and the project format
are unchanged — your existing projects keep working.

New in this release:

- **Release mode.** The API can serve the studio itself:
  `laqta studio --production` builds the frontend and serves the whole
  application from <http://127.0.0.1:8000>.
- An **error boundary** in the studio: a render error no longer blanks the
  app.
- `laqta doctor --json` for scripts and CI.
- `scripts/setup.ps1` — a first-class Windows install.
- `/api/health` now reports the **job worker** state (`degraded` when the
  worker is not running).

> If your tooling reads `/api/health`, the response gained a `worker` field.
> The `status` value is now `degraded` when the worker is stopped — it used
> to say `healthy` unconditionally.

---

## 0.1.0 → 0.1.1

### ⚠️ URL import is now disabled by default

`QATTA_ENABLE_URL_INGESTION` shipped as `True` and is now `False`: the
feature is **fail-closed** and needs an explicit opt-in, like every other path
that reaches the network.

If you use the YouTube import, add this to your `.env`:

```bash
QATTA_ENABLE_URL_INGESTION=true
```

Without it the import button stays visible and refuses with the reason —
nothing is downloaded. The per-import rights confirmation is mandatory
either way.

### The hosted paths are unchanged

`QATTA_ALLOW_CLOUD_APIS` and `QATTA_LLM_HOSTED_OPT_IN` still default to
`False`. If you had opted in, nothing changes — and the studio keeps
disclosing that transcript text leaves the machine.

### Toolchain

| | Before | Now |
|---|---|---|
| Node | 20+ | **22.12+** (the Vitest 5 requirement) |
| Python | 3.11+ | 3.11+ (unchanged) |
| Tailwind | 3 | 4 (the theme now lives in `src/index.css` — `@theme`) |

The upgrade is mechanical: `npm ci` in `frontend/` and `pip install -r
backend/requirements-dev.txt` in `backend/`.

### The API health response

`GET /api/health` gained a `worker` field and can now report `degraded`.
See the note above.

### The core test suite no longer writes to your data directory

`pytest tests` used to create real projects in `~/.local/share/qatta`
(you may find leftovers named "API Manifest Test" — they are safe to
delete). The suite is hermetic now.

---

## 0.0.x → 0.1.0

The first public release. See [CHANGELOG.md](../CHANGELOG.md).
